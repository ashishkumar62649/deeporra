"""Graph builder — create in-memory graph nodes and edges from parsed files."""

from collections import defaultdict
from typing import Any

from fcode.contracts.enums import (
    Confidence,
    GraphNodeType,
    GraphRelation,
    SymbolType,
)
from fcode.contracts.models import (
    GraphBuildResult,
    GraphEdgeInput,
    GraphNodeInput,
    ParsedFile,
    ParsedSymbol,
    ParsedImport,
    ParsedRoute,
)


def _node_id(node_type: GraphNodeType, label: str, *parts: str) -> str:
    base = f"{node_type.value}:{label}"
    if parts:
        base = f"{base}:{':'.join(parts)}"
    return base


def build(parsed_files: list[ParsedFile]) -> GraphBuildResult:
    nodes: list[GraphNodeInput] = []
    edges: list[GraphEdgeInput] = []
    node_map: dict[str, GraphNodeInput] = {}

    # qualified_name -> symbol_node mapping for cross-refs
    symbol_by_qn: dict[str, list[GraphNodeInput]] = defaultdict(list)

    for pf in parsed_files:
        file_nid = _node_id(GraphNodeType.FILE, pf.file_path)
        file_node = GraphNodeInput(
            external_id=file_nid,
            node_type=GraphNodeType.FILE,
            label=pf.file_path,
            properties={"file_path": pf.file_path},
            confidence=Confidence.EXTRACTED,
        )
        nodes.append(file_node)
        node_map[file_nid] = file_node

        for sym in pf.symbols:
            if sym.symbol_type == SymbolType.VARIABLE:
                continue

            type_map = {
                SymbolType.FUNCTION: GraphNodeType.SYMBOL,
                SymbolType.CLASS: GraphNodeType.SYMBOL,
                SymbolType.METHOD: GraphNodeType.SYMBOL,
            }
            nt = type_map.get(sym.symbol_type, GraphNodeType.SYMBOL)

            qualified = _qualified_name(pf.file_path, sym)

            props: dict[str, Any] = {
                "symbol_type": sym.symbol_type.value,
                "name": sym.name,
                "qualified_name": qualified,
                "start_line": sym.start_line,
                "end_line": sym.end_line,
                "file_path": pf.file_path,
            }
            if sym.docstring:
                props["docstring"] = sym.docstring

            sym_nid = _node_id(nt, qualified, pf.file_path, str(sym.start_line))
            sym_node = GraphNodeInput(
                external_id=sym_nid,
                node_type=nt,
                label=sym.name,
                properties=props,
                confidence=Confidence.EXTRACTED,
            )
            nodes.append(sym_node)
            node_map[sym_nid] = sym_node
            symbol_by_qn[qualified].append(sym_node)

            # defines edge
            edges.append(GraphEdgeInput(
                source_external_id=file_nid,
                target_external_id=sym_nid,
                relation=GraphRelation.DEFINES,
                properties={
                    "source_file": pf.file_path,
                    "source_location": f"L{sym.start_line}-L{sym.end_line}",
                },
                confidence=Confidence.EXTRACTED,
            ))

        for imp in pf.imports:
            import_nid = _node_id(GraphNodeType.SYMBOL, imp.module)
            import_node = GraphNodeInput(
                external_id=import_nid,
                node_type=GraphNodeType.SYMBOL,
                label=imp.module,
                properties={
                    "module_name": imp.module,
                    "imported_names": imp.names,
                    "line_number": imp.start_line,
                    "file_path": pf.file_path,
                },
                confidence=Confidence.EXTRACTED,
            )
            if import_nid not in node_map:
                nodes.append(import_node)
                node_map[import_nid] = import_node

            edges.append(GraphEdgeInput(
                source_external_id=file_nid,
                target_external_id=import_nid,
                relation=GraphRelation.IMPORTS,
                properties={
                    "module_name": imp.module,
                    "imported_names": imp.names,
                    "alias": None,
                    "line_number": imp.start_line,
                },
                confidence=Confidence.EXTRACTED,
            ))

        # Test projection for test files
        if _is_test_file(pf.file_path):
            for sym in pf.symbols:
                if sym.symbol_type in (SymbolType.FUNCTION, SymbolType.METHOD):
                    test_nid = _node_id(GraphNodeType.SYMBOL, f"test:{sym.name}", pf.file_path)
                    test_node = GraphNodeInput(
                        external_id=test_nid,
                        node_type=GraphNodeType.SYMBOL,
                        label=f"test:{sym.name}",
                        properties={
                            "symbol_type": sym.symbol_type.value,
                            "name": sym.name,
                            "file_path": pf.file_path,
                            "start_line": sym.start_line,
                            "end_line": sym.end_line,
                        },
                        confidence=Confidence.INFERRED,
                    )
                    nodes.append(test_node)
                    node_map[test_nid] = test_node

                    # defines edge for test
                    edges.append(GraphEdgeInput(
                        source_external_id=file_nid,
                        target_external_id=test_nid,
                        relation=GraphRelation.DEFINES,
                        properties={
                            "source_file": pf.file_path,
                            "source_location": f"L{sym.start_line}-L{sym.end_line}",
                        },
                        confidence=Confidence.INFERRED,
                    ))

        for route in pf.routes:
            route_label = f"{route.method.value} {route.path}"
            route_nid = _node_id(GraphNodeType.SYMBOL, f"route:{route.method.value}:{route.path}", pf.file_path)
            route_node = GraphNodeInput(
                external_id=route_nid,
                node_type=GraphNodeType.SYMBOL,
                label=route_label,
                properties={
                    "symbol_type": "route",
                    "http_method": route.method.value,
                    "route_path": route.path,
                    "handler_function": f"{_module_from_path(pf.file_path)}.{route.handler}",
                    "file_path": pf.file_path,
                    "line_number": route.start_line,
                    "name": route_label,
                },
                confidence=Confidence.EXTRACTED,
            )
            nodes.append(route_node)
            node_map[route_nid] = route_node

            edges.append(GraphEdgeInput(
                source_external_id=file_nid,
                target_external_id=route_nid,
                relation=GraphRelation.DEFINES,
                properties={
                    "source_file": pf.file_path,
                    "source_location": f"L{route.start_line}",
                },
                confidence=Confidence.EXTRACTED,
            ))

    # Edges: inherits
    for pf in parsed_files:
        for sym in pf.symbols:
            if sym.symbol_type == SymbolType.CLASS and sym.parent:
                child_nid = _node_id(GraphNodeType.SYMBOL, _qualified_name(pf.file_path, sym), pf.file_path, str(sym.start_line))
                for base_name in sym.parent.split(","):
                    base_qn = _qualified_name(pf.file_path, ParsedSymbol(name=base_name.strip(), symbol_type=SymbolType.CLASS, start_line=0, end_line=0))
                    match = symbol_by_qn.get(base_qn) or symbol_by_qn.get(base_name.strip())
                    if match:
                        parent_nid = match[0].external_id
                        edges.append(GraphEdgeInput(
                            source_external_id=child_nid,
                            target_external_id=parent_nid,
                            relation=GraphRelation.INHERITS,
                            properties={
                                "source_file": pf.file_path,
                                "source_location": f"L{sym.start_line}",
                            },
                            confidence=Confidence.EXTRACTED,
                        ))

    return GraphBuildResult(node_count=len(nodes), edge_count=len(edges), errors=[])


def _module_from_path(file_path: str) -> str:
    return file_path.replace(".py", "").replace(".pyw", "").replace("/", ".").replace("\\", ".")


def _qualified_name(file_path: str, sym: ParsedSymbol) -> str:
    module = file_path.replace(".py", "").replace(".pyw", "").replace("/", ".").replace("\\", ".")
    if sym.parent:
        return f"{module}.{sym.parent}.{sym.name}"
    return f"{module}.{sym.name}"


def _is_test_file(file_path: str) -> bool:
    parts = file_path.replace("\\", "/").split("/")
    return any(p in ("test", "tests") for p in parts) or file_path.startswith("test_") or "/test_" in file_path
