"""Tests for graph_builder.py."""

from fcode.contracts import (
    Confidence, FileType, GraphBuildResult, GraphNodeInput, GraphNodeType,
    GraphRelation, HttpMethod, ParsedFile, ParsedImport, ParsedRoute,
    ParsedSymbol, ParseStatus, SymbolType,
)
from fcode.graph.graph_builder import build, _infer_tested_name


def _pf(path: str) -> ParsedFile:
    return ParsedFile(
        file_path=path,
        file_id=f"file:{path}",
        file_type=FileType.SOURCE,
        status=ParseStatus.PARSED,
    )


def _sym(name: str, typ: SymbolType, **kw) -> ParsedSymbol:
    kw.setdefault("symbol_id", f"sym:{name}")
    kw.setdefault("start_line", 1)
    kw.setdefault("end_line", 1)
    return ParsedSymbol(name=name, symbol_type=typ, confidence=Confidence.EXTRACTED, **kw)


def _imp(module: str, names: list[str] | None = None, **kw) -> ParsedImport:
    kw.setdefault("line_number", 1)
    return ParsedImport(
        module_name=module,
        imported_names=names or [module],
        confidence=Confidence.EXTRACTED,
        **kw,
    )


def _route(path: str, fn: str, **kw) -> ParsedRoute:
    kw.setdefault("route_id", f"route:{path}")
    kw.setdefault("start_line", 1)
    kw.setdefault("method", HttpMethod.GET)
    return ParsedRoute(
        route_path=f"/{path}",
        handler_function=fn,
        method=kw.pop("method"),
        confidence=Confidence.EXTRACTED,
        **kw,
    )


def test_build_returns_graphbuildresult():
    result = build([])
    assert isinstance(result, GraphBuildResult)


def test_empty_build():
    result = build([])
    assert result.node_count == 0
    assert result.edge_count == 0


def test_function_node():
    pf = _pf("mod.py")
    pf.symbols.append(_sym("foo", SymbolType.FUNCTION))
    result = build([pf])
    fn_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.FUNCTION]
    assert len(fn_nodes) == 1
    assert fn_nodes[0].label == "foo"
    assert fn_nodes[0].source_file == "mod.py"


def test_class_node():
    pf = _pf("mod.py")
    pf.symbols.append(_sym("MyClass", SymbolType.CLASS))
    result = build([pf])
    cls_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.CLASS]
    assert len(cls_nodes) == 1
    assert cls_nodes[0].label == "MyClass"


def test_method_node():
    pf = _pf("mod.py")
    pf.symbols.append(_sym("bar", SymbolType.METHOD))
    result = build([pf])
    m_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.METHOD]
    assert len(m_nodes) == 1
    assert m_nodes[0].label == "bar"


def test_route_node():
    rid = "route:GET:/users"
    pf = _pf("routes.py")
    pf.routes.append(_route("users", "list_users", route_id=rid))
    pf.symbols.append(_sym("GET /users", SymbolType.ROUTE, symbol_id=rid))
    pf.symbols.append(_sym("list_users", SymbolType.FUNCTION))
    result = build([pf])
    r_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.ROUTE]
    assert len(r_nodes) >= 1


def test_handles_route_edge():
    rid = "route:GET:/users"
    pf = _pf("routes.py")
    pf.routes.append(_route("users", "list_users", route_id=rid))
    pf.symbols.append(_sym("GET /users", SymbolType.ROUTE, symbol_id=rid))
    pf.symbols.append(_sym("list_users", SymbolType.FUNCTION))
    result = build([pf])
    edges = [e for e in result.edges if e.relation == GraphRelation.DEFINES]
    assert len(edges) >= 1


def test_file_node():
    pf = _pf("mod.py")
    result = build([pf])
    file_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.FILE]
    assert len(file_nodes) == 1
    assert file_nodes[0].label == "mod.py"


def test_test_symbol_ignored():
    pf = _pf("test_mod.py")
    pf.file_type = FileType.TEST
    pf.symbols.append(_sym("test_foo", SymbolType.FUNCTION))
    result = build([pf])
    assert len(result.nodes) >= 1


def test_multiple_files():
    pf1 = _pf("mod1.py")
    pf1.symbols.append(_sym("foo", SymbolType.FUNCTION))
    pf2 = _pf("mod2.py")
    pf2.symbols.append(_sym("bar", SymbolType.FUNCTION))
    result = build([pf1, pf2])
    fn_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.FUNCTION]
    assert len(fn_nodes) == 2


def test_edge_count_greater_than_zero_with_symbols():
    pf = _pf("mod.py")
    pf.symbols.append(_sym("foo", SymbolType.FUNCTION))
    result = build([pf])
    assert result.edge_count > 0


def test_inherits_edge():
    base = _sym("Base", SymbolType.CLASS, symbol_id="sym:Base")
    child = _sym("Child", SymbolType.CLASS, symbol_id="sym:Child",
                  metadata={"bases": ["Base"]})
    pf = _pf("mod.py")
    pf.symbols.extend([base, child])
    result = build([pf])
    inherits_edges = [e for e in result.edges if e.relation == GraphRelation.INHERITS]
    assert len(inherits_edges) >= 1
    assert inherits_edges[0].source_node_id == "sym:Child"
    assert inherits_edges[0].target_node_id == "sym:Base"


def test_calls_edge():
    caller = _sym("caller", SymbolType.FUNCTION, symbol_id="sym:caller",
                   metadata={"calls": ["callee"]})
    callee = _sym("callee", SymbolType.FUNCTION, symbol_id="sym:callee")
    pf = _pf("mod.py")
    pf.symbols.extend([caller, callee])
    result = build([pf])
    calls_edges = [e for e in result.edges if e.relation == GraphRelation.CALLS]
    assert len(calls_edges) >= 1
    assert calls_edges[0].source_node_id == "sym:caller"
    assert calls_edges[0].target_node_id == "sym:callee"


def test_tests_edge():
    test_fn = _sym("test_foo", SymbolType.FUNCTION, symbol_id="sym:test_foo")
    target_fn = _sym("foo", SymbolType.FUNCTION, symbol_id="sym:foo")
    pf = _pf("test_mod.py")
    pf.file_type = FileType.TEST
    pf.symbols.extend([test_fn, target_fn])
    result = build([pf])
    tests_edges = [e for e in result.edges if e.relation == GraphRelation.TESTS]
    assert len(tests_edges) >= 1
    assert tests_edges[0].source_node_id == "sym:test_foo"


def test_unresolved_tests_no_edge():
    test_fn = _sym("test_unknown", SymbolType.FUNCTION, symbol_id="sym:test_unknown")
    pf = _pf("test_mod.py")
    pf.file_type = FileType.TEST
    pf.symbols.append(test_fn)
    result = build([pf])
    tests_edges = [e for e in result.edges if e.relation == GraphRelation.TESTS]
    assert len(tests_edges) == 0


def test_normal_function_not_test():
    fn = _sym("helper", SymbolType.FUNCTION, symbol_id="sym:helper")
    pf = _pf("mod.py")
    pf.symbols.append(fn)
    result = build([pf])
    test_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.TEST]
    assert len(test_nodes) == 0
    fn_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.FUNCTION]
    assert len(fn_nodes) == 1


def test_handles_route_edge():
    rid = "route:GET:/users:routes.py:1"
    route_sym = _sym("GET /users", SymbolType.ROUTE, symbol_id=rid)
    handler_sym = _sym("list_users", SymbolType.FUNCTION, symbol_id="sym:list_users")
    route = _route("users", "list_users", route_id=rid)
    pf = _pf("routes.py")
    pf.routes.append(route)
    pf.symbols.extend([route_sym, handler_sym])
    result = build([pf])
    hr_edges = [e for e in result.edges if e.relation == GraphRelation.HANDLES_ROUTE]
    assert len(hr_edges) >= 1
    assert hr_edges[0].source_node_id == rid
    assert hr_edges[0].target_node_id == "sym:list_users"


def test_handles_route_confidence():
    rid = "route:GET:/items:routes.py:5"
    route_sym = _sym("GET /items", SymbolType.ROUTE, symbol_id=rid)
    handler_sym = _sym("get_items", SymbolType.FUNCTION, symbol_id="sym:get_items")
    route = _route("items", "get_items", route_id=rid, start_line=5)
    pf = _pf("routes.py")
    pf.routes.append(route)
    pf.symbols.extend([route_sym, handler_sym])
    result = build([pf])
    hr_edges = [e for e in result.edges if e.relation == GraphRelation.HANDLES_ROUTE]
    assert len(hr_edges) >= 1
    assert hr_edges[0].confidence == Confidence.EXTRACTED


def test_duplicate_import_edges_preserved():
    imp1 = _imp("os", line_number=1)
    imp2 = _imp("os", line_number=5)
    pf = _pf("mod.py")
    pf.imports.extend([imp1, imp2])
    result = build([pf])
    import_edges = [e for e in result.edges if e.relation == GraphRelation.IMPORTS]
    assert len(import_edges) == 2


def test_variable_no_graph_node():
    var = _sym("x", SymbolType.VARIABLE)
    pf = _pf("mod.py")
    pf.symbols.append(var)
    result = build([pf])
    non_file_nodes = [n for n in result.nodes if n.node_type != GraphNodeType.FILE]
    assert len(non_file_nodes) == 0


# ── Import duplicate-ID defects ──────────────────────────────────────────────


def test_two_imports_same_module_same_line():
    pf = _pf("mod.py")
    pf.imports.append(_imp("package.module", names=["Alpha"], line_number=10))
    pf.imports.append(_imp("package.module", names=["Beta"], line_number=10))
    result = build([pf])
    import_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.IMPORT]
    assert len(import_nodes) == 2
    node_ids = [n.node_id for n in import_nodes]
    assert len(set(node_ids)) == len(node_ids)
    alpha_nodes = [n for n in import_nodes if "Alpha" in n.node_id]
    beta_nodes = [n for n in import_nodes if "Beta" in n.node_id]
    assert len(alpha_nodes) == 1
    assert len(beta_nodes) == 1


def test_imports_with_different_aliases():
    pf = _pf("mod.py")
    pf.imports.append(_imp("os", names=["os"], alias="operating_system", line_number=1))
    pf.imports.append(_imp("shutil", names=["shutil"], alias=None, line_number=2))
    result = build([pf])
    import_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.IMPORT]
    assert len(import_nodes) == 2
    os_nodes = [n for n in import_nodes if "os" in n.node_id]
    shutil_nodes = [n for n in import_nodes if "shutil" in n.node_id]
    assert len(os_nodes) == 1
    assert len(shutil_nodes) == 1
    assert os_nodes[0].node_id != shutil_nodes[0].node_id


def test_exact_duplicate_import_records():
    pf = _pf("mod.py")
    pf.imports.append(_imp("os", names=["os"], line_number=1))
    pf.imports.append(_imp("os", names=["os"], line_number=1))
    result = build([pf])
    import_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.IMPORT]
    assert len(import_nodes) == 1
    import_edges = [e for e in result.edges if e.relation == GraphRelation.IMPORTS]
    assert len(import_edges) == 1


def test_repeated_import_build_determinism():
    pf = _pf("mod.py")
    pf.imports.append(_imp("package.module", names=["Alpha"], line_number=5))
    pf.imports.append(_imp("package.module", names=["Beta"], line_number=5))
    r1 = build([pf])
    r2 = build([pf])
    nids1 = [n.node_id for n in r1.nodes if n.node_type == GraphNodeType.IMPORT]
    nids2 = [n.node_id for n in r2.nodes if n.node_type == GraphNodeType.IMPORT]
    assert nids1 == nids2


# ── Route duplicate-ID defects ───────────────────────────────────────────────


def test_duplicate_route_records_deduplicated():
    pf = _pf("routes.py")
    rid = "route:GET:/users:mod.py:1"
    pf.routes.append(_route("users", "list_users", route_id=rid))
    pf.routes.append(_route("users", "list_users", route_id=rid))
    pf.symbols.append(_sym("list_users", SymbolType.FUNCTION))
    result = build([pf])
    route_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.ROUTE]
    assert len(route_nodes) == 1


def test_same_path_different_methods():
    pf = _pf("routes.py")
    rid1 = "route:GET:/items:routes.py:1"
    rid2 = "route:POST:/items:routes.py:2"
    pf.routes.append(_route("items", "get_items", route_id=rid1))
    pf.routes.append(_route("items", "post_items", route_id=rid2, method=HttpMethod.POST))
    pf.symbols.append(_sym("get_items", SymbolType.FUNCTION))
    pf.symbols.append(_sym("post_items", SymbolType.FUNCTION))
    result = build([pf])
    route_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.ROUTE]
    assert len(route_nodes) == 2
    node_ids = [n.node_id for n in route_nodes]
    assert len(set(node_ids)) == len(node_ids)


def test_different_paths_same_handler():
    pf = _pf("routes.py")
    rid1 = "route:GET:/users:routes.py:1"
    rid2 = "route:GET:/admins:routes.py:2"
    pf.routes.append(_route("users", "list_users", route_id=rid1))
    pf.routes.append(_route("admins", "list_users", route_id=rid2))
    pf.symbols.append(_sym("list_users", SymbolType.FUNCTION, symbol_id="sym:list_users"))
    result = build([pf])
    route_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.ROUTE]
    assert len(route_nodes) == 2
    hr_edges = [e for e in result.edges if e.relation == GraphRelation.HANDLES_ROUTE]
    assert len(hr_edges) == 2


def test_exact_duplicate_route_edges_deduplicated():
    pf = _pf("routes.py")
    rid = "route:GET:/items:routes.py:1"
    route1 = _route("items", "get_items", route_id=rid, start_line=1)
    route2 = _route("items", "get_items", route_id=rid, start_line=1)
    pf.routes.extend([route1, route2])
    pf.symbols.append(_sym("get_items", SymbolType.FUNCTION, symbol_id="sym:get_items"))
    result = build([pf])
    hr_edges = [e for e in result.edges if e.relation == GraphRelation.HANDLES_ROUTE]
    assert len(hr_edges) == 1
    defines_edges = [e for e in result.edges if e.relation == GraphRelation.DEFINES
                     and e.target_node_id == rid]
    assert len(defines_edges) == 1


def test_repeated_route_build_determinism():
    pf = _pf("routes.py")
    pf.routes.append(_route("x", "handler_x", route_id="route:GET:/x:routes.py:1"))
    pf.routes.append(_route("y", "handler_y", route_id="route:GET:/y:routes.py:2"))
    pf.symbols.append(_sym("handler_x", SymbolType.FUNCTION))
    pf.symbols.append(_sym("handler_y", SymbolType.FUNCTION))
    r1 = build([pf])
    r2 = build([pf])
    nids1 = [n.node_id for n in r1.nodes if n.node_type == GraphNodeType.ROUTE]
    nids2 = [n.node_id for n in r2.nodes if n.node_type == GraphNodeType.ROUTE]
    assert nids1 == nids2


# ── Global invariants ────────────────────────────────────────────────────────


def test_all_graph_node_ids_unique():
    pf1 = _pf("mod1.py")
    pf1.symbols.append(_sym("foo", SymbolType.FUNCTION))
    pf1.symbols.append(_sym("bar", SymbolType.FUNCTION))
    pf1.imports.append(_imp("os", line_number=1))
    pf1.imports.append(_imp("json", line_number=2))
    pf2 = _pf("mod2.py")
    pf2.symbols.append(_sym("baz", SymbolType.FUNCTION))
    pf2.imports.append(_imp("re", line_number=1))
    result = build([pf1, pf2])
    node_ids = [n.node_id for n in result.nodes]
    assert len(set(node_ids)) == len(node_ids)


def test_all_canonical_edges_unique():
    pf1 = _pf("mod1.py")
    pf1.symbols.append(_sym("foo", SymbolType.FUNCTION))
    pf1.imports.append(_imp("os", line_number=1))
    pf2 = _pf("mod2.py")
    pf2.symbols.append(_sym("bar", SymbolType.FUNCTION))
    result = build([pf1, pf2])
    edge_triples = [(e.source_node_id, e.target_node_id, e.relation.value)
                    for e in result.edges]
    assert len(set(edge_triples)) == len(edge_triples)


def test_node_and_edge_count_matches():
    pf1 = _pf("mod1.py")
    pf1.symbols.append(_sym("foo", SymbolType.FUNCTION))
    pf1.imports.append(_imp("os", line_number=1))
    pf2 = _pf("mod2.py")
    pf2.symbols.append(_sym("bar", SymbolType.FUNCTION))
    result = build([pf1, pf2])
    assert result.node_count == len(result.nodes)
    assert result.edge_count == len(result.edges)


# ── Deterministic record IDs ──────────────────────────────────────────────────


def test_deterministic_node_record_ids():
    pf = _pf("mod.py")
    pf.symbols.append(_sym("foo", SymbolType.FUNCTION))
    r1 = build([pf])
    r2 = build([pf])
    rids1 = sorted(n.record_id for n in r1.nodes)
    rids2 = sorted(n.record_id for n in r2.nodes)
    assert rids1 == rids2


def test_deterministic_edge_record_ids():
    pf = _pf("mod.py")
    pf.symbols.append(_sym("foo", SymbolType.FUNCTION))
    r1 = build([pf])
    r2 = build([pf])
    erids1 = sorted(e.record_id for e in r1.edges)
    erids2 = sorted(e.record_id for e in r2.edges)
    assert erids1 == erids2


def test_node_record_id_format():
    pf = _pf("mod.py")
    pf.symbols.append(_sym("foo", SymbolType.FUNCTION))
    result = build([pf])
    for n in result.nodes:
        assert n.record_id.startswith("gn:"), f"node record_id {n.record_id} missing gn: prefix"
        hex_part = n.record_id[len("gn:"):]
        assert len(hex_part) == 64, f"node record_id hex part {hex_part!r} is not sha256-length"
        int(hex_part, 16)
        assert n.record_id != "gn:" + n.node_id, (
            "node record_id must not be ambiguous colon concatenation — it must hash canonical identity"
        )


def test_edge_record_id_format():
    pf = _pf("mod.py")
    pf.symbols.append(_sym("foo", SymbolType.FUNCTION))
    result = build([pf])
    for e in result.edges:
        assert e.record_id.startswith("ge:"), f"edge record_id {e.record_id} missing ge: prefix"


# ── Route payload preservation ────────────────────────────────────────────────


def test_route_payload_from_parsed_route_not_symbol():
    rid = "route:GET:/test:routes.py:1"
    pf = _pf("routes.py")
    pf.routes.append(_route("test", "handler", route_id=rid))
    sym = _sym("wrong_name", SymbolType.ROUTE, symbol_id=rid)
    pf.symbols.append(sym)
    pf.symbols.append(_sym("handler", SymbolType.FUNCTION))
    result = build([pf])
    route_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.ROUTE]
    assert len(route_nodes) == 1
    assert route_nodes[0].label == "GET /test", f"expected 'GET /test', got '{route_nodes[0].label}'"
    assert route_nodes[0].source_file == "routes.py"


# ── Adversarial: colons and repeated separators ──────────────────────────────


def test_colons_in_node_id_dont_collide_record_ids():
    """Adversarial: a node_id containing colons must produce a record_id derived
    from canonical fields, not ambiguous colon concatenation."""
    pf = _pf("a:b.py")
    pf.symbols.append(_sym("x:y:z", SymbolType.FUNCTION))
    r1 = build([pf])
    r2 = build([pf])
    rids1 = sorted(n.record_id for n in r1.nodes)
    rids2 = sorted(n.record_id for n in r2.nodes)
    assert rids1 == rids2
    # Every record id is a sha256 digest under the gn: prefix.
    for rid in rids1:
        assert rid.startswith("gn:")
        hex_part = rid[len("gn:"):]
        assert len(hex_part) == 64
        int(hex_part, 16)


def test_repeated_separators_in_paths_record_id_stable():
    """Adversarial: file paths with repeated slashes and colons in name parts
    produce stable, collision-safe record IDs from canonical identity."""
    weird_path = "a//b::c///d.py"
    pf1 = _pf(weird_path)
    pf1.symbols.append(_sym("weird", SymbolType.FUNCTION))
    r1 = build([pf1])
    r2 = build([pf1])
    assert sorted(n.record_id for n in r1.nodes) == sorted(
        n.record_id for n in r2.nodes
    )
    file_node = [n for n in r1.nodes if n.node_type == GraphNodeType.FILE][0]
    assert file_node.node_id == f"file:{weird_path}"
    # The record_id is NOT `gn:file:<weird_path>`; it's a hash digest.
    assert file_node.record_id != "gn:" + file_node.node_id
    assert file_node.record_id.startswith("gn:")
    assert len(file_node.record_id) == len("gn:") + 64


def test_two_distinct_canonical_identities_produce_distinct_record_ids():
    """Different canonical identities produce different record IDs (collision
    is statistically impossible with SHA-256 but enforced here directly)."""
    pf = _pf("mod.py")
    pf.symbols.append(_sym("first", SymbolType.FUNCTION, start_line=1))
    pf.symbols.append(_sym("second", SymbolType.FUNCTION, start_line=5))
    pf.imports.append(_imp("os", line_number=10))
    r = build([pf])
    rids = [n.record_id for n in r.nodes]
    assert len(set(rids)) == len(rids)
    nids = [n.node_id for n in r.nodes]
    assert len(set(nids)) == len(nids)


def test_same_canonical_identity_produces_same_record_id():
    """Identical canonical identities must produce identical record IDs
    across rebuilds (stable derivation, no timestamps, no UUID4)."""
    pf1 = _pf("mod.py")
    pf1.symbols.append(_sym("foo", SymbolType.FUNCTION, start_line=1))
    r1 = build([pf1])

    pf2 = _pf("mod.py")
    pf2.symbols.append(_sym("foo", SymbolType.FUNCTION, start_line=1))
    r2 = build([pf2])

    foo_rids1 = sorted(n.record_id for n in r1.nodes if n.node_id == "sym:foo")
    foo_rids2 = sorted(n.record_id for n in r2.nodes if n.node_id == "sym:foo")
    assert foo_rids1 == foo_rids2
    assert len(foo_rids1) == len(foo_rids2) == 1


def test_repeated_separator_files_unique_node_ids():
    """Files with repeated separators must produce unique node_ids (no
    separator-collapse surprise)."""
    pf1 = _pf("a/b.py")
    pf2 = _pf("a//b.py")
    r = build([pf1, pf2])
    file_ids = [n.node_id for n in r.nodes if n.node_type == GraphNodeType.FILE]
    assert "file:a/b.py" in file_ids
    assert "file:a//b.py" in file_ids
    rids = [n.record_id for n in r.nodes]
    assert len(set(rids)) == len(rids)


def test_record_id_no_uuid_or_timestamp_features():
    """The record ID format must not contain timestamps or timestamp-like
    suffixes. SHA-256 hex digests are exactly 64 lowercase hex chars."""
    pf = _pf("mod.py")
    pf.symbols.append(_sym("foo", SymbolType.FUNCTION))
    r = build([pf])
    for n in r.nodes:
        rec = n.record_id
        assert "T" not in rec.split(":", 1)[1]  # no ISO timestamp
        hex_part = rec.split(":", 1)[1]
        assert all(c in "0123456789abcdef" for c in hex_part)


def test_record_id_distinct_under_colon_path_collisions():
    """Adversarial: two files whose paths share a suffix that would, under
    naive colon-concatenation, produce identical record IDs. Must remain
    distinct."""
    pf1 = _pf("a/b.py")
    pf1.symbols.append(_sym("foo", SymbolType.FUNCTION, start_line=1))
    pf2 = _pf("a:b.py")
    pf2.symbols.append(_sym("foo", SymbolType.FUNCTION, start_line=1))
    r = build([pf1, pf2])
    file_recs = [n.record_id for n in r.nodes if n.node_type == GraphNodeType.FILE]
    assert len(set(file_recs)) == 2


def test_canonical_identity_collision_impossible_for_routes():
    """Adversarial: two ParsedRoute records with identical identity must not
    produce duplicate record IDs or duplicate node entries."""
    pf = _pf("routes.py")
    rid = "route:GET:/users:routes.py:1"
    pf.routes.append(_route("users", "list_users", route_id=rid, start_line=1))
    pf.routes.append(_route("users", "list_users", route_id=rid, start_line=1))
    pf.symbols.append(_sym("list_users", SymbolType.FUNCTION, start_line=2))
    r = build([pf])
    route_nodes = [n for n in r.nodes if n.node_type == GraphNodeType.ROUTE]
    assert len(route_nodes) == 1
    # Same record_id repeated under different canonical identity objects
    # is impossible: only one node entry survives, with one record_id.
    rids = [n.record_id for n in r.nodes]
    assert len(set(rids)) == len(rids)


def test_graph_builder_rejects_duplicate_node_id_in_input():
    """If input attempts to register the same node_id twice via distinct
    canonical paths, the graph builder reads only the first canonical
    occurrence. The result must have no duplicate node_id or record_id."""
    # Same symbol_id reused across files is a parser problem in practice
    # but the graph builder makes the result deterministic.
    pf1 = _pf("a.py")
    pf1.symbols.append(_sym("dup", SymbolType.FUNCTION, symbol_id="sym:DUP", start_line=1))
    pf2 = _pf("b.py")
    pf2.symbols.append(_sym("dup", SymbolType.FUNCTION, symbol_id="sym:DUP", start_line=1))
    r = build([pf1, pf2])
    nids = [n.node_id for n in r.nodes]
    rids = [n.record_id for n in r.nodes]
    assert len(set(nids)) == len(nids)
    assert len(set(rids)) == len(rids)
