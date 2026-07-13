"""F Code local Streamlit dashboard — read-only repository intelligence."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from fcode.dashboard.api import safe_impact, safe_related, safe_routes, safe_search, safe_summary, safe_symbols
from fcode.querying import QueryService, RepositoryNotIndexedError, RepositorySummary

# ── Page config ──────────────────────────────────────────────────────────

st.set_page_config(
    page_title="F Code Dashboard",
    page_icon="\u2139\ufe0f",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("## F Code Dashboard \u2014 Prototype")
st.markdown(
    "Local read-only repository intelligence. "
    "All data is stored locally on your machine. "
    "No code is sent to external services."
)

# ── Session state helpers ────────────────────────────────────────────────

_REPO_KEY = "dashboard_repository_root"
_QS_KEY = "dashboard_query_service"


def _reset_repo() -> None:
    for k in list(st.session_state.keys()):
        if k in (_REPO_KEY, _QS_KEY):
            del st.session_state[k]


def _get_qs() -> QueryService | None:
    return st.session_state.get(_QS_KEY)


def _connect_repo(path: str) -> str | None:
    p = Path(path).resolve()
    if not p.is_dir():
        return f"Path does not exist: {path}"
    try:
        qs = QueryService(str(p))
    except RepositoryNotIndexedError:
        return f"Repository at {p} is not indexed. Run `fcode index` first."
    except Exception as exc:
        return f"Could not connect to repository: {exc}"
    st.session_state[_REPO_KEY] = str(p)
    st.session_state[_QS_KEY] = qs
    return None


# ── Sidebar: repository input ───────────────────────────────────────────

st.sidebar.markdown("### Repository")
repo_input = st.sidebar.text_input(
    "Repository root path",
    value=st.session_state.get(_REPO_KEY, ""),
    placeholder="/path/to/repo",
    key="repo_path_input",
    on_change=_reset_repo,
)
if repo_input:
    err = _connect_repo(repo_input)
    if err:
        st.sidebar.error(err)

qs = _get_qs()
if qs is None:
    st.info(
        "Enter a repository root path in the sidebar to get started. "
        "The repository must already be indexed with `fcode index`."
    )
    st.stop()

# ── Navigation ──────────────────────────────────────────────────────────

page = st.sidebar.radio(
    "View",
    [
        "Repository Overview",
        "Code Search",
        "Symbols",
        "Routes",
        "Related Code",
        "Change Impact",
    ],
)

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**Local-only** \u00b7 Read-only \u00b7 "
    "Secrets are detected and redacted."
)


# ═══════════════════════════════════════════════════════════════════════════
# PAGE 1 — Repository Overview
# ═══════════════════════════════════════════════════════════════════════════

if page == "Repository Overview":
    st.subheader("Repository Overview")
    result = safe_summary(qs)
    if isinstance(result, str):
        st.error(result)
        st.stop()
    s = result
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Repository", s.repository_root)
        st.metric("Index Status", s.index_status)
    with col2:
        st.metric("Active Generation", s.active_generation_id)
        st.metric("Indexed At", s.indexed_at or "N/A")
    with col3:
        st.metric("File Count", s.file_count)
        st.metric("Symbol Count", s.symbol_count)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Parsed", s.parsed_count)
        st.metric("Not Applicable", s.not_applicable_count)
        st.metric("Errors", s.error_count)
    with col2:
        st.metric("Imports", s.import_count)
        st.metric("Routes", s.route_count)
        st.metric("Tests", s.test_count)
    with col3:
        st.metric("Chunks", s.chunk_count)
        st.metric("Graph Nodes", s.graph_node_count)
        st.metric("Graph Edges", s.graph_edge_count)
    if s.warning_count > 0 or s.fatal_error_count > 0:
        st.warning(f"Warnings: {s.warning_count}, Fatal errors: {s.fatal_error_count}")

# ═══════════════════════════════════════════════════════════════════════════
# PAGE 2 — Code Search
# ═══════════════════════════════════════════════════════════════════════════

elif page == "Code Search":
    st.subheader("Code Search")
    query = st.text_input("Search query", key="cs_query", placeholder="e.g. database connection")
    col1, col2, _ = st.columns([2, 1, 2])
    with col1:
        mode = st.selectbox("Search mode", ["text", "semantic", "hybrid"], index=0)
    with col2:
        limit = st.number_input("Max results", min_value=1, max_value=500, value=20, step=1)
    if st.button("Search", type="primary"):
        if not query.strip():
            st.warning("Please enter a search query.")
            st.stop()
        results = safe_search(qs, query.strip(), limit=int(limit), mode=mode)
        if isinstance(results, str):
            st.error(results)
            st.stop()
        if not results:
            st.info("No results found.")
            st.stop()
        if mode == "hybrid" and all(r.match_source == "text" for r in results):
            st.info("Hybrid mode degraded to text-only because the embedding model is unavailable.")
        for r in results:
            src = r.source_path.replace("\\", "/")
            st.markdown(f"**{src}** `{r.start_line}\u2013{r.end_line}`  Kind: {r.chunk_kind}  Owner: {r.owner_semantic_key or 'N/A'}")
            st.text(r.display_text[:500] if r.display_text else "")
            score_parts = []
            if r.text_score is not None:
                score_parts.append(f"Text: {r.text_score:.3f}")
            if r.semantic_score is not None:
                score_parts.append(f"Semantic: {r.semantic_score:.3f}")
            score_parts.append(f"Combined: {r.combined_score:.3f}")
            score_parts.append(f"Source: {r.match_source}")
            st.caption(" | ".join(score_parts))
            st.divider()

# ═══════════════════════════════════════════════════════════════════════════
# PAGE 3 — Symbols
# ═══════════════════════════════════════════════════════════════════════════

elif page == "Symbols":
    st.subheader("Symbol Lookup")
    sym_query = st.text_input("Symbol name", key="sym_query", placeholder="e.g. Calculator")
    col1, col2, _ = st.columns([1, 1, 2])
    with col1:
        exact = st.checkbox("Exact match", value=False)
    with col2:
        sym_limit = st.number_input("Max results", min_value=1, max_value=500, value=20, step=1)
    if st.button("Find Symbols", type="primary"):
        if not sym_query.strip():
            st.warning("Please enter a symbol name.")
            st.stop()
        results = safe_symbols(qs, sym_query.strip(), limit=int(sym_limit), exact=exact)
        if isinstance(results, str):
            st.error(results)
            st.stop()
        if not results:
            st.info("No symbols found.")
            st.stop()
        for sym in results:
            src = sym.source_path.replace("\\", "/")
            parent = sym.parent_semantic_key or ""
            st.markdown(f"**{sym.qualified_name}**  Type: {sym.kind}  File: {src}:{sym.start_line}\u2013{sym.end_line}")
            if parent:
                st.caption(f"Parent: {parent}")
            st.divider()

# ═══════════════════════════════════════════════════════════════════════════
# PAGE 4 — Routes
# ═══════════════════════════════════════════════════════════════════════════

elif page == "Routes":
    st.subheader("Route Lookup")
    col1, col2, col3, col4 = st.columns([1, 2, 2, 1])
    with col1:
        http_method = st.text_input("HTTP method", placeholder="GET", key="rt_method")
    with col2:
        path_q = st.text_input("Path query", placeholder="/api", key="rt_path")
    with col3:
        handler_q = st.text_input("Handler", placeholder="get_items", key="rt_handler")
    with col4:
        rt_limit = st.number_input("Limit", min_value=1, max_value=500, value=50, step=1)
    if st.button("Find Routes", type="primary"):
        results = safe_routes(qs, method=http_method.strip() or None, path_q=path_q.strip() or None, handler_q=handler_q.strip() or None, limit=int(rt_limit))
        if isinstance(results, str):
            st.error(results)
            st.stop()
        if not results:
            st.info("No routes found.")
            st.stop()
        for route in results:
            src = route.source_path.replace("\\", "/")
            st.markdown(f"**{route.http_method}** `{route.route_path}`  \u2192 {route.handler_name}  File: {src}:{route.decorator_line}")
            st.caption(f"Handler: {route.handler_semantic_key}  Lines: {route.handler_start_line}\u2013{route.handler_end_line}")
            st.divider()

# ═══════════════════════════════════════════════════════════════════════════
# PAGE 5 — Related Code
# ═══════════════════════════════════════════════════════════════════════════

elif page == "Related Code":
    st.subheader("Related Code (One Hop)")
    rel_key = st.text_input("Semantic key (node ID or symbol key)", key="rel_key", placeholder="e.g. Calculator.add")
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        direction = st.selectbox("Direction", ["both", "outgoing", "incoming"], index=0)
    with col2:
        edge_types = st.text_input("Edge types (comma-separated, optional)", placeholder="calls,imports", key="rel_edges")
    with col3:
        rel_limit = st.number_input("Limit", min_value=1, max_value=500, value=100, step=1)
    if st.button("Find Related", type="primary"):
        if not rel_key.strip():
            st.warning("Please enter a semantic key.")
            st.stop()
        edge_list = [e.strip() for e in edge_types.split(",") if e.strip()] if edge_types.strip() else None
        results = safe_related(qs, rel_key.strip(), direction=direction, edge_types=edge_list, limit=int(rel_limit))
        if isinstance(results, str):
            st.error(results)
            st.stop()
        if not results:
            st.info("No related nodes found.")
            st.stop()
        for n in results:
            src = n.source_path.replace("\\", "/") if n.source_path else ""
            st.markdown(f"**{n.qualified_name}** ({n.node_kind})  Relation: {n.relationship_type}  Direction: {n.direction}")
            st.caption(f"Node: {n.related_node_identity}  File: {src}")
            if n.qualifier:
                st.caption(f"Qualifier: {n.qualifier}")
            st.divider()

# ═══════════════════════════════════════════════════════════════════════════
# PAGE 6 — Change Impact
# ═══════════════════════════════════════════════════════════════════════════

elif page == "Change Impact":
    st.subheader("Change Impact Analysis")
    st.info("**FIRST-ORDER IMPACT ONLY** — This shows only direct relationships. It does not represent transitive or complete impact analysis.")
    imp_key = st.text_input("Semantic key (symbol or node ID)", key="imp_key", placeholder="e.g. Calculator.add")
    imp_limit = st.number_input("Max results per category", min_value=1, max_value=500, value=100, step=1)
    if st.button("Analyze Impact", type="primary"):
        if not imp_key.strip():
            st.warning("Please enter a semantic key.")
            st.stop()
        result = safe_impact(qs, imp_key.strip(), limit=int(imp_limit))
        if isinstance(result, str):
            st.error(result)
            st.stop()
        st.markdown(f"### Target: {result['target']}")
        st.markdown(f"**Kind:** {result['kind']}  \n**File:** {result['source_path']}")
        st.caption(f"Analysis type: {result['analysis_type']}")
        if result["warnings"]:
            st.warning("\n".join(result["warnings"]))
        if result["direct_callers"]:
            st.markdown("#### Direct Callers")
            for c in result["direct_callers"]:
                src = c.source_path.replace("\\", "/")
                st.markdown(f"`{c.qualified_name}` — {src}:{c.start_line}")
        if result["direct_callees"]:
            st.markdown("#### Direct Callees")
            for c in result["direct_callees"]:
                src = c.source_path.replace("\\", "/")
                st.markdown(f"`{c.qualified_name}` — {src}:{c.start_line}")
        if result["containing_file"]:
            st.markdown(f"#### Containing File\n`{result['containing_file']}`")
        if result["containing_class"]:
            st.markdown(f"#### Containing Class\n`{result['containing_class']}`")
        if result["import_relationships"]:
            st.markdown("#### Import Relationships")
            for r in result["import_relationships"]:
                st.markdown(f"`{r.qualified_name}` ({r.relationship_type}, {r.direction})")
        if result["route_relationships"]:
            st.markdown("#### Route Relationships")
            for r in result["route_relationships"]:
                st.markdown(f"`{r.qualified_name}` ({r.relationship_type})")
        if result["related_tests"]:
            st.markdown("#### Directly Represented Tests")
            for t in result["related_tests"]:
                src = t.source_path.replace("\\", "/")
                st.markdown(f"`{t.qualified_name}` — {src}:{t.start_line}")
