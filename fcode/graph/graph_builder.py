"""Graph builder — build a code graph from parsed files."""

import uuid
from typing import Sequence

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


def build(parsed_files: Sequence[ParsedFile]) -> GraphBuildResult:
    return build_graph(parsed_files)


def build_graph(parsed_files: Sequence[ParsedFile]) -> GraphBuildResult:
    nodes: list[GraphNodeInput] = []
    edges: list[GraphEdgeInput] = []

    symbol_by_id: dict[str, ParsedSymbol] = {}
    symbol_by_name: dict[str, list[ParsedSymbol]] = {}
    node_id_for_sym_id: dict[str, str] = {}

    for pf in parsed_files:
        file_node_id = f"file:{pf.file_path}"
        nodes.append(
            GraphNodeInput(
                record_id=str(uuid.uuid4()),
                node_id=file_node_id,
                node_type=GraphNodeType.FILE,
                label=pf.file_path,
                source_file=pf.file_path,
                confidence=Confidence.EXTRACTED,
            )
        )

        symbol_nodes: dict[str, str] = {}

        for sym in pf.symbols:
            node_type = _symbol_to_node_type(sym, pf.file_type)
            if node_type is None:
                continue

            node_id = sym.symbol_id or f"{sym.symbol_type.value}:{pf.file_path}:{sym.name}:{sym.start_line}"
            symbol_nodes[sym.symbol_id or node_id] = node_id
            symbol_by_id[node_id] = sym
            symbol_by_name.setdefault(sym.name, []).append(sym)
            node_id_for_sym_id[sym.symbol_id or node_id] = node_id

            nodes.append(
                GraphNodeInput(
                    record_id=str(uuid.uuid4()),
                    node_id=node_id,
                    node_type=node_type,
                    label=sym.name,
                    source_file=pf.file_path,
                    source_location=f"{pf.file_path}:{sym.start_line}",
                    confidence=sym.confidence,
                )
            )
            edges.append(
                GraphEdgeInput(
                    record_id=str(uuid.uuid4()),
                    source_node_id=file_node_id,
                    target_node_id=node_id,
                    relation=GraphRelation.DEFINES,
                    source_file=pf.file_path,
                    source_location=f"{pf.file_path}:{sym.start_line}",
                    confidence=Confidence.EXTRACTED,
                )
            )

            if sym.parent_symbol_id:
                parent_id = sym.parent_symbol_id
                if parent_id in symbol_nodes:
                    edges.append(
                        GraphEdgeInput(
                            record_id=str(uuid.uuid4()),
                            source_node_id=parent_id,
                            target_node_id=node_id,
                            relation=GraphRelation.DEFINES,
                            source_file=pf.file_path,
                            source_location=f"{pf.file_path}:{sym.start_line}",
                            confidence=Confidence.INFERRED,
                        )
                    )

        for imp in pf.imports:
            import_node_id = f"import:{pf.file_path}:{imp.module_name}:{imp.line_number}"
            nodes.append(
                GraphNodeInput(
                    record_id=str(uuid.uuid4()),
                    node_id=import_node_id,
                    node_type=GraphNodeType.IMPORT,
                    label=imp.module_name,
                    source_file=pf.file_path,
                    source_location=f"{pf.file_path}:{imp.line_number}",
                    confidence=imp.confidence,
                    metadata={
                        "module_name": imp.module_name,
                        "imported_names": imp.imported_names,
                        "alias": imp.alias,
                        "line_number": imp.line_number,
                    },
                )
            )
            edges.append(
                GraphEdgeInput(
                    record_id=str(uuid.uuid4()),
                    source_node_id=file_node_id,
                    target_node_id=import_node_id,
                    relation=GraphRelation.IMPORTS,
                    source_file=pf.file_path,
                    source_location=f"{pf.file_path}:{imp.line_number}",
                    confidence=Confidence.EXTRACTED,
                    metadata={
                        "module_name": imp.module_name,
                        "imported_names": imp.imported_names,
                        "alias": imp.alias,
                        "line_number": imp.line_number,
                    },
                )
            )

        for route in pf.routes:
            route_node_id = route.route_id

            nodes.append(
                GraphNodeInput(
                    record_id=str(uuid.uuid4()),
                    node_id=route_node_id,
                    node_type=GraphNodeType.ROUTE,
                    label=f"{route.method.value} {route.route_path}",
                    source_file=pf.file_path,
                    source_location=f"{pf.file_path}:{route.start_line}",
                    confidence=route.confidence,
                )
            )

            handler_id: str | None = None
            for sym in pf.symbols:
                if sym.name == route.handler_function and sym.symbol_type in (SymbolType.FUNCTION, SymbolType.METHOD):
                    handler_id = sym.symbol_id
                    break

            if handler_id:
                edges.append(
                    GraphEdgeInput(
                        record_id=str(uuid.uuid4()),
                        source_node_id=handler_id,
                        target_node_id=route_node_id,
                        relation=GraphRelation.DEFINES,
                        source_file=pf.file_path,
                        source_location=f"{pf.file_path}:{route.start_line}",
                        confidence=Confidence.EXTRACTED,
                    )
                )
                edges.append(
                    GraphEdgeInput(
                        record_id=str(uuid.uuid4()),
                        source_node_id=route_node_id,
                        target_node_id=handler_id,
                        relation=GraphRelation.HANDLES_ROUTE,
                        source_file=pf.file_path,
                        source_location=f"{pf.file_path}:{route.start_line}",
                        confidence=Confidence.EXTRACTED,
                    )
                )

    _add_inherits_edges(edges, symbol_by_id, symbol_by_name, node_id_for_sym_id)
    _add_calls_edges(edges, symbol_by_id, symbol_by_name, node_id_for_sym_id)
    _add_tests_edges(edges, symbol_by_id, symbol_by_name, node_id_for_sym_id)

    _sort_nodes(nodes)
    _sort_edges(edges)

    return GraphBuildResult(
        nodes=nodes,
        edges=edges,
        node_count=len(nodes),
        edge_count=len(edges),
    )


def _add_inherits_edges(
    edges: list[GraphEdgeInput],
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
                        edges.append(
                            GraphEdgeInput(
                                record_id=str(uuid.uuid4()),
                                source_node_id=source_node_id,
                                target_node_id=target_node_id,
                                relation=GraphRelation.INHERITS,
                                source_file="",
                                source_location=f"{sym.symbol_id}:{sym.start_line}",
                                confidence=Confidence.EXTRACTED,
                            )
                        )


def _add_calls_edges(
    edges: list[GraphEdgeInput],
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
                        edges.append(
                            GraphEdgeInput(
                                record_id=str(uuid.uuid4()),
                                source_node_id=source_node_id,
                                target_node_id=target_node_id,
                                relation=GraphRelation.CALLS,
                                source_file="",
                                source_location=f"{sym.symbol_id}:{sym.start_line}",
                                confidence=Confidence.INFERRED,
                            )
                        )


def _add_tests_edges(
    edges: list[GraphEdgeInput],
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
                        edges.append(
                            GraphEdgeInput(
                                record_id=str(uuid.uuid4()),
                                source_node_id=source_node_id,
                                target_node_id=target_node_id,
                                relation=GraphRelation.TESTS,
                                source_file="",
                                source_location=f"{sym.symbol_id}:{sym.start_line}",
                                confidence=Confidence.INFERRED,
                            )
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
