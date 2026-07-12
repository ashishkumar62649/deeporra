"""Schema version 2 — exact active index count snapshot."""

SCHEMA_VERSION = 2
SCHEMA_DESCRIPTION = "Persist canonical active index counts"

COUNT_COLUMNS = (
    "count_scanned", "count_parsed", "count_graph_nodes", "count_graph_edges",
    "count_chunks", "count_embedded", "count_parse_errors", "count_symbols",
    "count_embedding_eligible", "count_embedding_skipped", "count_embedding_failed",
    "count_warnings", "count_errors",
)


def apply(conn):
    """Add exact-count columns without changing existing rows or meanings."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(index_status)")}
    for column in COUNT_COLUMNS:
        if column not in existing:
            conn.execute(f"ALTER TABLE index_status ADD COLUMN {column} INTEGER")
    conn.execute(
        "INSERT OR REPLACE INTO schema_version (version, description) VALUES (?, ?)",
        (SCHEMA_VERSION, SCHEMA_DESCRIPTION),
    )
