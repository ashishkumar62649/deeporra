"""Strict test-only schema checks for future WP6 semantic manifests."""

import re

REQUIRED = {"fixture_id", "fixture_name", "purpose", "scanned_files", "excluded_files", "parse_statuses", "symbols", "imports", "routes", "tests", "chunks", "graph_nodes", "graph_edges", "safe_search_terms", "warnings", "errors", "secret_oracle", "deterministic_invariants"}
RECORDS = {
    "parse_statuses": {"path", "status", "language", "diagnostic_category"},
    "symbols": {"semantic_key", "kind", "qualified_name", "path", "start_line", "end_line", "parent_semantic_key"},
    "imports": {"source_path", "source_module", "imported_module", "imported_name", "alias", "kind"},
    "routes": {"method", "route_path", "handler_semantic_key", "source_path", "start_line", "end_line"},
    "tests": {"semantic_key", "qualified_name", "source_path", "start_line", "end_line", "referenced_semantic_keys"},
    "chunks": {"semantic_key", "source_path", "chunk_type", "owner_semantic_key", "start_line", "end_line", "embedding_eligible", "skip_reason"},
    "graph_nodes": {"semantic_key", "kind", "qualified_name", "source_path", "linked_semantic_key"},
    "graph_edges": {"source_semantic_key", "target_semantic_key", "edge_type", "qualifier"},
}


def _fail(section, message):
    raise ValueError(f"{section}: {message}")


def _path(section, value):
    if not isinstance(value, str) or not value or "\\" in value or value.startswith(("/", ".fcode")) or re.match(r"^[A-Za-z]:", value) or ".." in value.split("/"):
        _fail(section, "must be a normalized repository-relative path")
    if any(token in value.lower() for token in (".db", ".sqlite", "chroma", "generation-", "active.json", "rebuild.lock")):
        _fail(section, "contains a generated artifact path")


def _lines(section, record):
    if "start_line" in record and (not isinstance(record["start_line"], int) or not isinstance(record["end_line"], int) or record["start_line"] < 1 or record["start_line"] > record["end_line"]):
        _fail(section, "has invalid line range")


def validate_manifest(manifest):
    if not isinstance(manifest, dict): _fail("manifest", "must be an object")
    if set(manifest) != REQUIRED: _fail("manifest", f"required fields mismatch: {sorted(REQUIRED - set(manifest)) or sorted(set(manifest) - REQUIRED)}")
    if not all(isinstance(manifest[k], str) and manifest[k] for k in ("fixture_id", "fixture_name", "purpose")): _fail("manifest", "fixture identity must be non-empty")
    for section in ("scanned_files", "excluded_files"):
        if not isinstance(manifest[section], list): _fail(section, "must be a list")
        for value in manifest[section]: _path(section, value)
    for section, fields in RECORDS.items():
        records = manifest[section]
        if not isinstance(records, list): _fail(section, "must be a list")
        seen = set()
        for index, record in enumerate(records):
            if not isinstance(record, dict) or set(record) != fields: _fail(f"{section}[{index}]", "record fields mismatch")
            for key in ("path", "source_path"):
                if key in record: _path(f"{section}[{index}].{key}", record[key])
            _lines(f"{section}[{index}]", record)
            key = (record.get("semantic_key") or (record.get("method"), record.get("route_path"), record.get("handler_semantic_key")) or (record.get("source_semantic_key"), record.get("target_semantic_key"), record.get("edge_type"), record.get("qualifier")))
            if record.get("semantic_key") and re.fullmatch(r"[0-9a-f]{8}-[0-9a-f-]{27}", record["semantic_key"]): _fail(section, "uses an opaque generated ID")
            if key in seen: _fail(section, "contains duplicate semantic identity")
            seen.add(key)
    symbols = {x["semantic_key"] for x in manifest["symbols"]}; nodes = {x["semantic_key"] for x in manifest["graph_nodes"]}
    for symbol in manifest["symbols"]:
        if symbol["parent_semantic_key"] is not None and symbol["parent_semantic_key"] not in symbols: _fail("symbols", "parent references unknown symbol")
    for route in manifest["routes"]:
        if route["handler_semantic_key"] not in symbols: _fail("routes", "handler references unknown symbol")
    for chunk in manifest["chunks"]:
        if chunk["owner_semantic_key"] is not None and chunk["owner_semantic_key"] not in symbols: _fail("chunks", "owner references unknown symbol")
    for edge in manifest["graph_edges"]:
        if edge["source_semantic_key"] not in nodes or edge["target_semantic_key"] not in nodes: _fail("graph_edges", "references unknown node")
    secret = manifest["secret_oracle"]
    if not isinstance(secret, dict) or set(secret) != {"labels", "sha256_digests", "redaction_markers", "safe_neighbor_terms"}: _fail("secret_oracle", "must contain labels, digests, markers, terms only")
    if any("TEST_ONLY_" in str(value) for value in manifest.values()): _fail("manifest", "contains raw secret material")
    if not isinstance(manifest["deterministic_invariants"], dict): _fail("deterministic_invariants", "must be an object")
