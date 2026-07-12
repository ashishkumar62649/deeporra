# F Code

Local-first Python repository indexing for AI coding workflows.

F Code safely indexes a local repository: it scans and redacts secrets, parses Python with `ast`, creates semantic chunks and local embeddings, persists SQLite/FTS5, Chroma, and graph data, then promotes a verified local generation.

## Available now

- `fcode index [repo]` — full local rebuild with safe active-generation promotion.
- `fcode status [repo]` — active-generation state and canonical persisted counts.
- `fcode doctor [repo]` — offline readiness checks for Python, dependencies, SQLite FTS5, and the locked local embedding model.
- Python AST analysis, chunking, local embeddings, SQLite/FTS5, local Chroma, graph persistence, and secret redaction.

```bash
pip install -e .
fcode doctor /path/to/repo
fcode index /path/to/repo
fcode status /path/to/repo
```

`fcode doctor` never downloads the model. Install the locked local model `sentence-transformers/all-MiniLM-L6-v2` before indexing.

## Deferred

- MCP user workflow
- Dashboard user workflow
- Retrieval/search CLI
- Agent setup workflow
- Incremental indexing
- Automatic source edits

The `dashboard`, `mcp`, and `setup` commands are safe deferred stubs and exit 2.

## Privacy

All indexed data remains local. F Code does not upload repository source, use hosted embeddings, or expose a network service.

## Testing

Run the current suite with:

```bash
python -m pytest -q -ra
```

## Documentation

Authoritative implementation requirements are `AGENTS.md` and `docs/01_CONTEXT.md` through `docs/09_AGENT_TASKS.md`.
