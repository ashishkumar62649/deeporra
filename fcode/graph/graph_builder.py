"""Graph builder — build a code graph from parsed files.

Identity contract (WP5 Step 3 closure):
- Node identity is derived from stable, alias-free canonical fields.
- Record IDs are collision-safe: compact JSON of canonical fields with fixed
  key order, hashed via SHA-256. The prefix `gn:` for nodes and `ge:` for
  edges keeps record IDs visually distinct from node IDs.
- Canonical identity is used as the dedup key. No dict ordering, no path
  manipulation, no colons may produce collisions.
- Output invariant: every successful result has unique node_ids, unique
  node record_ids, unique canonical edge tuples, unique edge record_ids,
  and every edge endpoint references a known node.

The builder in the first slice may ONLY:
- Convert files into file nodes
- Convert parsed symbols into symbol nodes (function, class, method, route, test)
- Convert imports into import nodes
- Connect routes to handler functions
- Connect tests to detected target symbols when evidence is directly extractable
- Produce `GraphNodeInput` and `GraphEdgeInput` records
- Apply confidence vocabulary: `EXTRACTED`, `INFERRED`, `AMBIGUOUS`
"""

import hashlib
import json
from typing import Any, Sequence

from fcode.contracts import (
    Confidence,
    FileType,
    GraphBuildResult,
    GraphEdgeInput,
    GraphNodeInput,
    GraphNodeType,
    GraphRelation,
    ParsedFile,
    ParsedSymbol,
    SymbolType,
)


SCHEMA_VERSION = "wp5.step3.graph.v1"
NODE_RECORD_PREFIX = "gn:"
EDGE_RECORD_PREFIX = "ge:"


def _canonical_record_id(prefix: str, canonical: dict[str, Any]) -> str:
    """Deterministic, collision-safe record ID from canonical fields.

    `canonical` is serialized as compact JSON with keys in fixed sorted order,
    then SHA-256 hex-encoded into a stable 64-character digest. The prefix
    keeps node records visually distinct from edge records.
    """
    payload = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{prefix}{digest}"


def _json_default(value: Any) -> Any:
    if isinstance(value, (SymbolType, GraphRelation, GraphNodeType, FileType, Confidence)):
        return value.value
    raise TypeError(f"unserializable canonical identity field: {type(value).__name__}")


def _node_canonical(node_id: str, node_type: GraphNodeType) -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "kind": "node",
        "node_id": node_id,
        "node_type": node_type.value,
    }


def _edge_canonical(
    source_node_id: str,
    target_node_id: str,
    relation: GraphRelation,
    source_file: str,
    source_location: str,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "kind": "edge",
        "source_node_id": source_node_id,
        "target_node_id": target_node_id,
        "relation": relation.value,
        "source_file": source_file,
        "source_location": source_location,
    }


def build(parsed_files: Sequence[ParsedFile]) -> GraphBuildResult:
    return build_graph(parsed_files)


def build_graph(parsed_files: Sequence[ParsedFile]) -> GraphBuildResult:
    nodes: list[GraphNodeInput] = []
    edges: list[GraphEdgeInput] = []

    symbol_by_id: dict[str, ParsedSymbol] = {}
    symbol_by_name: dict[str, list[ParsedSymbol]] = {}
    node_id_for_sym_id: dict[str, str] = {}

    seen_canonical_nodes: set[str] = set()
    seen_canonical_edges: set[str] = set()
    node_id_set: set[str] = set()
    node_record_id_set: set[str] = set()
    edge_record_id_set: set[str] = set()

    # Nodes seen in deterministic construction order to make edge endpoints
    # resolvable as we append — symbol nodes that depend on later symbol
    # IDs are normalised below.
    pending_handler_subs: list[tuple[int, str]] = []

    for pf in parsed_files:
        file_node_id = f"file:{pf.file_path}"
        nodes, node_id_set, node_record_id_set, seen_canonical_nodes = _add_node(
            nodes,
            node_id_set,
            node_record_id_set,
            seen_canonical_nodes,
            GraphNodeInput(
                record_id=_node_record_id(file_node_id, GraphNodeType.FILE),
                node_id=file_node_id,
                node_type=GraphNodeType.FILE,
                label=pf.file_path,
                source_file=pf.file_path,
                confidence=Confidence.EXTRACTED,
            ),
        )

        # Routes are processed first so their canonical identity is the
        # authoritative representation when a ParsedRoute-derived symbol node
        # shares the same node_id. Route payloads carry the method, path,
        # handler, and decorators which the symbol alone does not.
        for route in pf.routes:
            route_node_id = route.route_id
            payload = GraphNodeInput(
                record_id=_node_record_id(route_node_id, GraphNodeType.ROUTE),
                node_id=route_node_id,
                node_type=GraphNodeType.ROUTE,
                label=f"{route.method.value} {route.route_path}",
                source_file=pf.file_path,
                source_location=f"{pf.file_path}:{route.start_line}",
                confidence=route.confidence,
                metadata={
                    "http_method": route.method.value,
                    "route_path": route.route_path,
                    "handler_function": route.handler_function,
                    "decorators": list(route.decorators) if route.decorators else [],
                },
            )
            nodes, node_id_set, node_record_id_set, seen_canonical_nodes = _add_node(
                nodes,
                node_id_set,
                node_record_id_set,
                seen_canonical_nodes,
                payload,
            )

            handler_id: str | None = None
            for sym in pf.symbols:
                if sym.name == route.handler_function and sym.symbol_type in (SymbolType.FUNCTION, SymbolType.METHOD):
                    handler_id = sym.symbol_id
                    break

            if handler_id:
                edges, edge_record_id_set, seen_canonical_edges = _add_edge(
                    edges,
                    edge_record_id_set,
                    seen_canonical_edges,
                    GraphEdgeInput(
                        record_id=_edge_record_id(
                            handler_id,
                            GraphRelation.DEFINES,
                            route_node_id,
                            pf.file_path,
                            f"{pf.file_path}:{route.start_line}",
                        ),
                        source_node_id=handler_id,
                        target_node_id=route_node_id,
                        relation=GraphRelation.DEFINES,
                        source_file=pf.file_path,
                        source_location=f"{pf.file_path}:{route.start_line}",
                        confidence=Confidence.EXTRACTED,
                    ),
                )
                edges, edge_record_id_set, seen_canonical_edges = _add_edge(
                    edges,
                    edge_record_id_set,
                    seen_canonical_edges,
                    GraphEdgeInput(
                        record_id=_edge_record_id(
                            route_node_id,
                            GraphRelation.HANDLES_ROUTE,
                            handler_id,
                            pf.file_path,
                            f"{pf.file_path}:{route.start_line}",
                        ),
                        source_node_id=route_node_id,
                        target_node_id=handler_id,
                        relation=GraphRelation.HANDLES_ROUTE,
                        source_file=pf.file_path,
                        source_location=f"{pf.file_path}:{route.start_line}",
                        confidence=Confidence.EXTRACTED,
                    ),
                )

        symbol_nodes: dict[str, str] = {}

        for sym in pf.symbols:
            node_type = _symbol_to_node_type(sym, pf.file_type)
            if node_type is None:
                continue

            base_id = sym.symbol_id or f"{sym.symbol_type.value}:{pf.file_path}:{sym.name}:{sym.start_line}"
            node_id = base_id
            symbol_nodes[sym.symbol_id or base_id] = node_id
            if node_id not in symbol_by_id:
                symbol_by_id[node_id] = sym
            symbol_by_name.setdefault(sym.name, []).append(sym)
            node_id_for_sym_id[sym.symbol_id or base_id] = node_id

            # If the symbol's node_id is already in the graph (e.g. it is the
            # route_id of an authoritative ParsedRoute represented above),
            # skip emitting a redundant node but still register the symbol so
            # inherits/calls/tests edges continue to work.
            if node_id in node_id_set:
                continue

            nodes, node_id_set, node_record_id_set, seen_canonical_nodes = _add_node(
                nodes,
                node_id_set,
                node_record_id_set,
                seen_canonical_nodes,
                GraphNodeInput(
                    record_id=_node_record_id(node_id, node_type),
                    node_id=node_id,
                    node_type=node_type,
                    label=sym.name,
                    source_file=pf.file_path,
                    source_location=f"{pf.file_path}:{sym.start_line}",
                    confidence=sym.confidence,
                ),
            )

            edges, edge_record_id_set, seen_canonical_edges = _add_edge(
                edges,
                edge_record_id_set,
                seen_canonical_edges,
                GraphEdgeInput(
                    record_id=_edge_record_id(
                        file_node_id,
                        GraphRelation.DEFINES,
                        node_id,
                        pf.file_path,
                        f"{pf.file_path}:{sym.start_line}",
                    ),
                    source_node_id=file_node_id,
                    target_node_id=node_id,
                    relation=GraphRelation.DEFINES,
                    source_file=pf.file_path,
                    source_location=f"{pf.file_path}:{sym.start_line}",
                    confidence=Confidence.EXTRACTED,
                ),
            )

            if sym.parent_symbol_id:
                parent_id = sym.parent_symbol_id
                if parent_id in symbol_nodes:
                    edges, edge_record_id_set, seen_canonical_edges = _add_edge(
                        edges,
                        edge_record_id_set,
                        seen_canonical_edges,
                        GraphEdgeInput(
                            record_id=_edge_record_id(
                                parent_id,
                                GraphRelation.DEFINES,
                                node_id,
                                pf.file_path,
                                f"{pf.file_path}:{sym.start_line}",
                            ),
                            source_node_id=parent_id,
                            target_node_id=node_id,
                            relation=GraphRelation.DEFINES,
                            source_file=pf.file_path,
                            source_location=f"{pf.file_path}:{sym.start_line}",
                            confidence=Confidence.INFERRED,
                        ),
                    )

        for imp in pf.imports:
            identity = imp.imported_names[0] if imp.imported_names else imp.module_name
            import_node_id = f"import:{pf.file_path}:{imp.module_name}:{identity}:{imp.line_number}"

            nodes, node_id_set, node_record_id_set, seen_canonical_nodes = _add_node(
                nodes,
                node_id_set,
                node_record_id_set,
                seen_canonical_nodes,
                GraphNodeInput(
                    record_id=_node_record_id(import_node_id, GraphNodeType.IMPORT),
                    node_id=import_node_id,
                    node_type=GraphNodeType.IMPORT,
                    label=imp.module_name,
                    source_file=pf.file_path,
                    source_location=f"{pf.file_path}:{imp.line_number}",
                    confidence=imp.confidence,
                    metadata={
                        "module_name": imp.module_name,
                        "imported_names": list(imp.imported_names),
                        "alias": imp.alias,
                        "line_number": imp.line_number,
                    },
                ),
            )

            edges, edge_record_id_set, seen_canonical_edges = _add_edge(
                edges,
                edge_record_id_set,
                seen_canonical_edges,
                GraphEdgeInput(
                    record_id=_edge_record_id(
                        file_node_id,
                        GraphRelation.IMPORTS,
                        import_node_id,
                        pf.file_path,
                        f"{pf.file_path}:{imp.line_number}",
                    ),
                    source_node_id=file_node_id,
                    target_node_id=import_node_id,
                    relation=GraphRelation.IMPORTS,
                    source_file=pf.file_path,
                    source_location=f"{pf.file_path}:{imp.line_number}",
                    confidence=Confidence.EXTRACTED,
                    metadata={
                        "module_name": imp.module_name,
                        "imported_names": list(imp.imported_names),
                        "alias": imp.alias,
                        "line_number": imp.line_number,
                    },
                ),
            )

    # Append edges for inherits, calls, and tests. These use canonical
    # dedup so order between alphabetic and reverse doesn't matter.
    _add_inherits_edges(edges, edge_record_id_set, seen_canonical_edges, node_id_set,
                         symbol_by_id, symbol_by_name, node_id_for_sym_id)
    _add_calls_edges(edges, edge_record_id_set, seen_canonical_edges, node_id_set,
                       symbol_by_id, symbol_by_name, node_id_for_sym_id)
    _add_tests_edges(edges, edge_record_id_set, seen_canonical_edges, node_id_set,
                       symbol_by_id, symbol_by_name, node_id_for_sym_id)

    _enforce_invariants(nodes, edges, node_record_id_set, edge_record_id_set, node_id_set)

    _sort_nodes(nodes)
    _sort_edges(edges)

    return GraphBuildResult(
        nodes=nodes,
        edges=edges,
        node_count=len(nodes),
        edge_count=len(edges),
    )


def _node_record_id(node_id: str, node_type: GraphNodeType) -> str:
    return _canonical_record_id(
        NODE_RECORD_PREFIX,
        _node_canonical(node_id, node_type),
    )


def _edge_record_id(
    source_node_id: str,
    relation: GraphRelation,
    target_node_id: str,
    source_file: str,
    source_location: str,
) -> str:
    return _canonical_record_id(
        EDGE_RECORD_PREFIX,
        _edge_canonical(source_node_id, target_node_id, relation, source_file, source_location),
    )


def _add_node(
    nodes: list[GraphNodeInput],
    node_id_set: set[str],
    node_record_id_set: set[str],
    seen_canonical_nodes: set[str],
    node: GraphNodeInput,
) -> tuple[list[GraphNodeInput], set[str], set[str], set[str]]:
    key = _node_canonical(node.node_id, node.node_type)
    sig = _signature(key)
    if sig in seen_canonical_nodes:
        return nodes, node_id_set, node_record_id_set, seen_canonical_nodes
    if not node.node_id:
        raise ValueError("graph_builder: empty node_id rejected")
    if node.node_id in node_id_set:
        raise ValueError(
            f"graph_builder: duplicate node_id would corrupt graph: {node.node_id!r}"
        )
    if node.record_id in node_record_id_set:
        raise ValueError(
            f"graph_builder: duplicate node record_id would corrupt graph: {node.record_id!r}"
        )
    seen_canonical_nodes.add(sig)
    node_id_set.add(node.node_id)
    node_record_id_set.add(node.record_id)
    nodes.append(node)
    return nodes, node_id_set, node_record_id_set, seen_canonical_nodes


def _add_edge(
    edges: list[GraphEdgeInput],
    edge_record_id_set: set[str],
    seen_canonical_edges: set[str],
    edge: GraphEdgeInput,
) -> tuple[list[GraphEdgeInput], set[str], set[str]]:
    key = _edge_canonical(
        edge.source_node_id,
        edge.target_node_id,
        edge.relation,
        edge.source_file or "",
        edge.source_location or "",
    )
    sig = _signature(key)
    if sig in seen_canonical_edges:
        return edges, edge_record_id_set, seen_canonical_edges
    seen_canonical_edges.add(sig)
    edge_record_id_set.add(edge.record_id)
    edges.append(edge)
    return edges, edge_record_id_set, seen_canonical_edges


def _signature(canonical: dict[str, Any]) -> str:
    payload = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _enforce_invariants(
    nodes: list[GraphNodeInput],
    edges: list[GraphEdgeInput],
    node_record_id_set: set[str],
    edge_record_id_set: set[str],
    node_id_set: set[str],
) -> None:
    """Final post-construction invariant check.

    If any duplicate slips past incremental dedup, this raises immediately
    rather than producing a corrupt graph result. All check failures also
    include the offending value for debugging.
    """
    if len(node_record_id_set) != len(nodes):
        seen: set[str] = set()
        for n in nodes:
            if n.record_id in seen:
                raise ValueError(
                    f"graph_builder invariant: duplicate node record_id at post-check: {n.record_id!r}"
                )
            seen.add(n.record_id)
        raise ValueError("graph_builder invariant: node record_id set cardinality mismatch")

    if len(edge_record_id_set) != len(edges):
        seen_e: set[str] = set()
        for e in edges:
            if e.record_id in seen_e:
                raise ValueError(
                    f"graph_builder invariant: duplicate edge record_id at post-check: {e.record_id!r}"
                )
            seen_e.add(e.record_id)
        raise ValueError("graph_builder invariant: edge record_id set cardinality mismatch")

    for e in edges:
        if e.source_node_id not in node_id_set:
            raise ValueError(
                f"graph_builder invariant: edge source_node_id not in graph: {e.source_node_id!r}"
            )
        if e.target_node_id not in node_id_set:
            raise ValueError(
                f"graph_builder invariant: edge target_node_id not in graph: {e.target_node_id!r}"
            )


def _add_inherits_edges(
    edges: list[GraphEdgeInput],
    edge_record_id_set: set[str],
    seen_canonical_edges: set[str],
    node_id_set: set[str],
    symbol_by_id: dict[str, ParsedSymbol],
    symbol_by_name: dict[str, list[ParsedSymbol]],
    node_id_for_sym_id: dict[str, str],
) -> None:
    for sym_id, sym in list(symbol_by_id.items()):
        if sym.symbol_type != SymbolType.CLASS:
            continue
        bases = (sym.metadata or {}).get("bases", [])
        if not bases:
            continue
        source_node_id = node_id_for_sym_id.get(sym.symbol_id or sym_id)
        if not source_node_id:
            continue
        for base_name in bases:
            target_syms = symbol_by_name.get(base_name, [])
            for target in target_syms:
                if target.symbol_type == SymbolType.CLASS:
                    target_node_id = node_id_for_sym_id.get(target.symbol_id)
                    if target_node_id:
                        edges, edge_record_id_set, seen_canonical_edges = _add_edge(
                            edges,
                            edge_record_id_set,
                            seen_canonical_edges,
                            GraphEdgeInput(
                                record_id=_edge_record_id(
                                    source_node_id,
                                    GraphRelation.INHERITS,
                                    target_node_id,
                                    "",
                                    f"{sym.symbol_id}:{sym.start_line}",
                                ),
                                source_node_id=source_node_id,
                                target_node_id=target_node_id,
                                relation=GraphRelation.INHERITS,
                                source_file="",
                                source_location=f"{sym.symbol_id}:{sym.start_line}",
                                confidence=Confidence.EXTRACTED,
                            ),
                        )


def _add_calls_edges(
    edges: list[GraphEdgeInput],
    edge_record_id_set: set[str],
    seen_canonical_edges: set[str],
    node_id_set: set[str],
    symbol_by_id: dict[str, ParsedSymbol],
    symbol_by_name: dict[str, list[ParsedSymbol]],
    node_id_for_sym_id: dict[str, str],
) -> None:
    for sym_id, sym in list(symbol_by_id.items()):
        if sym.symbol_type not in (SymbolType.FUNCTION, SymbolType.METHOD):
            continue
        calls = (sym.metadata or {}).get("calls", [])
        if not calls:
            continue
        source_node_id = node_id_for_sym_id.get(sym.symbol_id or sym_id)
        if not source_node_id:
            continue
        for call_name in calls:
            target_syms = symbol_by_name.get(call_name, [])
            for target in target_syms:
                if target.symbol_type in (SymbolType.FUNCTION, SymbolType.METHOD):
                    target_node_id = node_id_for_sym_id.get(target.symbol_id)
                    if target_node_id and target_node_id != source_node_id:
                        edges, edge_record_id_set, seen_canonical_edges = _add_edge(
                            edges,
                            edge_record_id_set,
                            seen_canonical_edges,
                            GraphEdgeInput(
                                record_id=_edge_record_id(
                                    source_node_id,
                                    GraphRelation.CALLS,
                                    target_node_id,
                                    "",
                                    f"{sym.symbol_id}:{sym.start_line}",
                                ),
                                source_node_id=source_node_id,
                                target_node_id=target_node_id,
                                relation=GraphRelation.CALLS,
                                source_file="",
                                source_location=f"{sym.symbol_id}:{sym.start_line}",
                                confidence=Confidence.INFERRED,
                            ),
                        )


def _add_tests_edges(
    edges: list[GraphEdgeInput],
    edge_record_id_set: set[str],
    seen_canonical_edges: set[str],
    node_id_set: set[str],
    symbol_by_id: dict[str, ParsedSymbol],
    symbol_by_name: dict[str, list[ParsedSymbol]],
    node_id_for_sym_id: dict[str, str],
) -> None:
    for sym_id, sym in list(symbol_by_id.items()):
        node_type = _symbol_to_node_type(sym, FileType.SOURCE)
        if node_type != GraphNodeType.TEST:
            continue
        source_node_id = node_id_for_sym_id.get(sym.symbol_id or sym_id)
        if not source_node_id:
            continue
        tested_name = _infer_tested_name(sym.name)
        if tested_name:
            target_syms = symbol_by_name.get(tested_name, [])
            for target in target_syms:
                if target.symbol_type in (SymbolType.FUNCTION, SymbolType.METHOD, SymbolType.CLASS):
                    target_node_id = node_id_for_sym_id.get(target.symbol_id)
                    if target_node_id:
                        edges, edge_record_id_set, seen_canonical_edges = _add_edge(
                            edges,
                            edge_record_id_set,
                            seen_canonical_edges,
                            GraphEdgeInput(
                                record_id=_edge_record_id(
                                    source_node_id,
                                    GraphRelation.TESTS,
                                    target_node_id,
                                    "",
                                    f"{sym.symbol_id}:{sym.start_line}",
                                ),
                                source_node_id=source_node_id,
                                target_node_id=target_node_id,
                                relation=GraphRelation.TESTS,
                                source_file="",
                                source_location=f"{sym.symbol_id}:{sym.start_line}",
                                confidence=Confidence.INFERRED,
                            ),
                        )


def _infer_tested_name(name: str) -> str | None:
    if name.startswith("test_"):
        return name[5:]
    return None


def _symbol_to_node_type(sym, file_type: FileType) -> GraphNodeType | None:
    if sym.symbol_type == SymbolType.VARIABLE:
        return None
    if sym.symbol_type == SymbolType.FUNCTION:
        if file_type == FileType.TEST or sym.name.startswith("test_"):
            return GraphNodeType.TEST
        return GraphNodeType.FUNCTION
    if sym.symbol_type == SymbolType.CLASS:
        return GraphNodeType.CLASS
    if sym.symbol_type == SymbolType.METHOD:
        if file_type == FileType.TEST or sym.name.startswith("test_"):
            return GraphNodeType.TEST
        return GraphNodeType.METHOD
    if sym.symbol_type == SymbolType.ROUTE:
        return GraphNodeType.ROUTE
    return GraphNodeType.FILE


def _sort_nodes(nodes: list[GraphNodeInput]):
    nodes.sort(key=lambda n: (
        n.source_file or "",
        n.source_location or "",
        n.node_type.value if n.node_type else "",
        n.node_id or "",
    ))


def _sort_edges(edges: list[GraphEdgeInput]):
    edges.sort(key=lambda e: (
        e.source_file or "",
        e.source_location or "",
        e.relation.value if e.relation else "",
        e.source_node_id or "",
        e.target_node_id or "",
    ))
