# G01 Exact Semantic Mismatch Adjudication

## 1. Repository context

- Repository: `E:/Project/AI_Codebase_Onboarding_Agent-wp6`
- Branch: `wp6-acceptance`
- Starting HEAD: `ce453bb8827f0ca7b47cd17eb2cff1173bcc12b9`
- Required ancestor resolution: `0`
- Required ancestor check: `0`
- Starting worktree: clean
- Evidence-only scope: this document only
- IndexService/SQLite/Chroma/embeddings/CLI: not run

The accepted exact-comparison harness is
`tests/acceptance/test_wp6_g01_exact_semantics.py` at commit
`ce453bb8827f0ca7b47cd17eb2cff1173bcc12b9`.

## 2. Exact failure reproduction

Command:

```text
python -m pytest -q tests/acceptance/test_wp6_g01_exact_semantics.py -ra
```

Result: `1 failed, 2 passed in 0.13s`, with zero skipped, xfailed,
deselected, or error tests.

```text
EXACT_TEST_FAILURE_REPRODUCED=True
FAILING_NODE_ID=tests/acceptance/test_wp6_g01_exact_semantics.py::test_g01_production_semantics_exactly_match_manifest
EXPECTED_SYMBOL_COUNT=11
ACTUAL_SYMBOL_COUNT=11
EXPECTED_CHUNK_COUNT=19
ACTUAL_CHUNK_COUNT=19
EXPECTED_GRAPH_NODE_COUNT=21
ACTUAL_GRAPH_NODE_COUNT=18
EXPECTED_GRAPH_EDGE_COUNT=21
ACTUAL_GRAPH_EDGE_COUNT=19
```

The exact structured failures are:

```text
COLLECTION=symbols EXPECTED_COUNT=11 ACTUAL_COUNT=11
DUPLICATES=[] MISSING=[] UNEXPECTED=[]
FIELD_MISMATCHES=[class:routes:GreetingService actual end_line=13 expected end_line=14]

COLLECTION=chunks EXPECTED_COUNT=19 ACTUAL_COUNT=19
DUPLICATES=[] MISSING=[class:routes:GreetingService:8-14]
UNEXPECTED=[class:routes:GreetingService:8-13] FIELD_MISMATCHES=[]

COLLECTION=graph_nodes EXPECTED_COUNT=21 ACTUAL_COUNT=18
DUPLICATES=[]
MISSING=[file:guide.rst, file:README.md, file:settings.toml,
        test:tests/TestRoutes.py:test_greeting_service:4,
        import:service/routes.py:fastapi:fastapi:1]
UNEXPECTED=[function:tests/TestRoutes.py:test_greeting_service:4,
            import:service/routes.py:fastapi:FastAPI:1]
FIELD_MISMATCHES=[]

COLLECTION=graph_edges EXPECTED_COUNT=21 ACTUAL_COUNT=19
DUPLICATES=[]
MISSING=[class:service/routes.py:GreetingService:8 -> method:service/routes.py:greet:9 [defines],
        class:service/routes.py:GreetingService:8 -> method:service/routes.py:_audit:12 [defines],
        file:tests/TestRoutes.py -> test:tests/TestRoutes.py:test_greeting_service:4 [defines],
        file:service/routes.py -> import:service/routes.py:fastapi:fastapi:1 [imports]]
UNEXPECTED=[file:tests/TestRoutes.py -> function:tests/TestRoutes.py:test_greeting_service:4 [defines],
            file:service/routes.py -> import:service/routes.py:fastapi:FastAPI:1 [imports]]
FIELD_MISMATCHES=[]
```

## 3. Class-boundary evidence

Fixture source, lines 6 through 16:

```text
6:
7:
8: class GreetingService:
9:     def greet(self, name: str) -> str:
10:         return f"{DEFAULT_GREETING}, {normalize_name(name)}"
11:
12:     def _audit(self, user_id: str) -> str:
13:         return f"audit:{user_id}"
14:
15:
16: @app.get("/profiles/{user_id}")
```

Line 14 is a blank line. The last syntactic line belonging to the class is
line 13.

| Evidence source | Start | End | Includes blank line 14 | Authority |
|---|---:|---:|---|---|
| Source syntax | 8 | 13 | No | Direct fixture source |
| Python AST `ClassDef` | 8 | 13 | No | Python AST implementation contract |
| Production symbol | 8 | 13 | No | `symbol_extractor.py:38-49` uses `ast.ClassDef.end_lineno` |
| Production class chunk | 8 | 13 | No | `chunker.py:300-312,326-338` copies symbol range |
| Manifest symbol | 8 | 14 | Yes | Accepted manifest oracle |
| Manifest class chunk | 8 | 14 | Yes | Accepted manifest oracle |

Direct runtime evidence:

```text
ast.ClassDef.lineno=8
ast.ClassDef.end_lineno=13
production_symbol.start_line=8
production_symbol.end_line=13
production_class_chunk.start_line=8
production_class_chunk.end_line=13
manifest_symbol.start_line=8
manifest_symbol.end_line=14
manifest_class_chunk.start_line=8
manifest_class_chunk.end_line=14
```

`fcode/parser/symbol_extractor.py:39` reads `node.end_lineno` for class
symbols. `fcode/chunking/chunker.py:300` reads the source using the symbol
range, and `:331-332` copies `sym.start_line` and `sym.end_line` to the
chunk. The focused tests cover class extraction and class chunk creation;
the implementation supplies the exact boundary for this fixture.

```text
CLASS_END_LINE_CORRECT_VALUE=13
CLASS_CHUNK_END_LINE_CORRECT_VALUE=13
BLANK_LINES_INCLUDED_IN_AST_SYMBOL_RANGE=False
CLASS_MISMATCH_CLASSIFICATION=manifest-oracle defect
```

The class-chunk mismatch is the corresponding range manifestation of the
same accepted-oracle error, not a separate chunker boundary defect.

## 4. Exact-comparison projection audit

The actual builder completes before `_expected()` is called:

- scanner and parser construction: `test_wp6_g01_exact_semantics.py:59-68`;
- chunk construction: `:152-194`;
- graph construction: `:196`;
- expected manifest load: `:265-268`;
- comparison: `:321-355`.

The projection uses these raw production fields:

| Projected field | Raw production source | Normalization performed | Expected manifest consulted |
|---|---|---|---|
| Graph semantic key | `GraphNodeInput.node_id`, `:203-205` | None; retained as the production node ID | No |
| Graph node kind | `GraphNodeInput.node_type.value`, `:218-222` | Enum to string | No |
| Graph qualified name | `node.label`, or route metadata `handler_function`, or parsed symbol qualified name, `:206-217` | Route/symbol display normalization only | No |
| Graph source path | `GraphNodeInput.source_file`, `:223` | Backslashes to `/` | No |
| Graph linked semantic key | actual route-owner map or parsed symbol map, `:207-217` | Test-only canonical owner mapping | No |
| Edge source key | `GraphEdgeInput.source_node_id`, `:227-231` | None | No |
| Edge target key | `GraphEdgeInput.target_node_id`, `:227-231` | None | No |
| Edge type | `GraphEdgeInput.relation.value`, `:231` | Enum to string | No |
| Edge qualifier | No qualifier field exists on `GraphEdgeInput`; projection emits `None`, `:232` | Canonical null | No |

The expected manifest is not read by `_actual_static`; it is loaded only
after actual output is fully produced. The projection does not remove an
actual graph record after `build()` returns. It also does not rewrite the
raw graph node kind: the test node's raw `node_type` is `GraphNodeType.TEST`
even though its raw `node_id` has a `function:` prefix.

```text
PROJECTION_USES_EXPECTED_IDENTITIES=False
PROJECTION_FILTERS_GRAPH_NODES=False
PROJECTION_REWRITES_NODE_KINDS=False
PROJECTION_COLLAPSES_DUPLICATES=False
PROJECTION_DEFECT_FOUND=True
```

The defect is at the graph-input boundary inside the exact harness, not in
the field projection: `_actual_static()` builds `graph = build(parsed)` at
line 196, where `parsed` contains only the four Python parse candidates.
The graph builder therefore never receives `guide.rst`, `README.md`, or
`settings.toml`. The graph builder itself adds one file node for every
`ParsedFile` it receives at `fcode/graph/graph_builder.py:121-135`.

The duplicate helper checks `Counter` identities before constructing the
unique-record dictionaries (`test_wp6_g01_exact_semantics.py:297-307`).
No duplicate actual graph node or edge identity was observed.

## 5. Expected graph nodes

The following table is the complete accepted-manifest graph-node collection.

| # | Semantic key | Kind | Qualified name | Source path | Linked semantic key |
|---:|---|---|---|---|---|
| 1 | `file:guide.rst` | file | guide.rst | guide.rst | — |
| 2 | `file:README.md` | file | README.md | README.md | — |
| 3 | `file:service/__init__.py` | file | service/__init__.py | service/__init__.py | — |
| 4 | `file:service/helpers.py` | file | service/helpers.py | service/helpers.py | — |
| 5 | `file:service/routes.py` | file | service/routes.py | service/routes.py | — |
| 6 | `file:settings.toml` | file | settings.toml | settings.toml | — |
| 7 | `file:tests/TestRoutes.py` | file | tests/TestRoutes.py | tests/TestRoutes.py | — |
| 8 | `route:GET:/profiles/{user_id}:service/routes.py:16` | route | get_profile | service/routes.py | `function:routes:get_profile` |
| 9 | `route:POST:/profiles:service/routes.py:21` | route | create_profile | service/routes.py | `function:routes:create_profile` |
| 10 | `function:service/helpers.py:normalize_name:4` | function | normalize_name | service/helpers.py | `function:helpers:normalize_name` |
| 11 | `function:service/helpers.py:fetch_profile:8` | function | fetch_profile | service/helpers.py | `async_function:helpers:fetch_profile` |
| 12 | `class:service/routes.py:GreetingService:8` | class | GreetingService | service/routes.py | `class:routes:GreetingService` |
| 13 | `method:service/routes.py:greet:9` | method | GreetingService.greet | service/routes.py | `method:routes:GreetingService.greet` |
| 14 | `method:service/routes.py:_audit:12` | method | GreetingService._audit | service/routes.py | `method:routes:GreetingService._audit` |
| 15 | `function:service/routes.py:get_profile:17` | function | get_profile | service/routes.py | `function:routes:get_profile` |
| 16 | `function:service/routes.py:create_profile:22` | function | create_profile | service/routes.py | `function:routes:create_profile` |
| 17 | `test:tests/TestRoutes.py:test_greeting_service:4` | test | test_greeting_service | tests/TestRoutes.py | `test:tests:test_greeting_service` |
| 18 | `import:service/routes.py:fastapi:fastapi:1` | import | fastapi | service/routes.py | — |
| 19 | `import:service/routes.py:helpers:DEFAULT_GREETING:3` | import | helpers | service/routes.py | — |
| 20 | `import:service/routes.py:helpers:fetch_profile:3` | import | helpers | service/routes.py | — |
| 21 | `import:service/routes.py:helpers:normalize_name:3` | import | helpers | service/routes.py | — |

```text
EXPECTED_FILE_NODES=7
EXPECTED_SYMBOL_NODES=8
EXPECTED_ROUTE_NODES=2
EXPECTED_IMPORT_NODES=4
EXPECTED_OTHER_NODES=0
EXPECTED_TOTAL_NODES=21
```

The symbol-node count includes the test node and excludes variables and the
two route pseudo-symbols.

## 6. Actual graph nodes

This table is the complete actual `GraphBuildResult.nodes` projection. It is
not reconstructed from the manifest.

| # | Semantic key | Kind | Qualified name | Source path | Linked semantic key |
|---:|---|---|---|---|---|
| 1 | `file:service/__init__.py` | file | service/__init__.py | service/__init__.py | — |
| 2 | `file:service/helpers.py` | file | service/helpers.py | service/helpers.py | — |
| 3 | `function:service/helpers.py:normalize_name:4` | function | normalize_name | service/helpers.py | `function:helpers:normalize_name` |
| 4 | `function:service/helpers.py:fetch_profile:8` | function | fetch_profile | service/helpers.py | `async_function:helpers:fetch_profile` |
| 5 | `file:service/routes.py` | file | service/routes.py | service/routes.py | — |
| 6 | `import:service/routes.py:fastapi:FastAPI:1` | import | fastapi | service/routes.py | — |
| 7 | `method:service/routes.py:_audit:12` | method | GreetingService._audit | service/routes.py | `method:routes:GreetingService._audit` |
| 8 | `route:GET:/profiles/{user_id}:service/routes.py:16` | route | get_profile | service/routes.py | `function:routes:get_profile` |
| 9 | `function:service/routes.py:get_profile:17` | function | get_profile | service/routes.py | `function:routes:get_profile` |
| 10 | `route:POST:/profiles:service/routes.py:21` | route | create_profile | service/routes.py | `function:routes:create_profile` |
| 11 | `function:service/routes.py:create_profile:22` | function | create_profile | service/routes.py | `function:routes:create_profile` |
| 12 | `import:service/routes.py:helpers:DEFAULT_GREETING:3` | import | helpers | service/routes.py | — |
| 13 | `import:service/routes.py:helpers:fetch_profile:3` | import | helpers | service/routes.py | — |
| 14 | `import:service/routes.py:helpers:normalize_name:3` | import | helpers | service/routes.py | — |
| 15 | `class:service/routes.py:GreetingService:8` | class | GreetingService | service/routes.py | `class:routes:GreetingService` |
| 16 | `method:service/routes.py:greet:9` | method | GreetingService.greet | service/routes.py | `method:routes:GreetingService.greet` |
| 17 | `file:tests/TestRoutes.py` | file | tests/TestRoutes.py | tests/TestRoutes.py | — |
| 18 | `function:tests/TestRoutes.py:test_greeting_service:4` | test | test_greeting_service | tests/TestRoutes.py | `test:tests:test_greeting_service` |

```text
ACTUAL_FILE_NODES=4
ACTUAL_SYMBOL_NODES=8
ACTUAL_ROUTE_NODES=2
ACTUAL_IMPORT_NODES=4
ACTUAL_OTHER_NODES=0
ACTUAL_TOTAL_NODES=18
```

The actual symbol count is eight when the raw `test` node is included with
ordinary symbol kinds. The actual file count is four because only four
Python `ParsedFile` records were supplied to `build()`.

## 7. Exact graph-node differences

```text
MISSING_EXPECTED_GRAPH_NODE_KEYS=[
  file:guide.rst,
  file:README.md,
  file:settings.toml,
  test:tests/TestRoutes.py:test_greeting_service:4,
  import:service/routes.py:fastapi:fastapi:1
]

UNEXPECTED_ACTUAL_GRAPH_NODE_KEYS=[
  function:tests/TestRoutes.py:test_greeting_service:4,
  import:service/routes.py:fastapi:FastAPI:1
]

COMMON_GRAPH_NODE_KEYS=16
COMMON_NODE_FIELD_MISMATCHES=[]
DUPLICATE_ACTUAL_GRAPH_NODE_KEYS=[]
```

| Identity | Expected record | Actual record | Source construct | Contract evidence | Classification |
|---|---|---|---|---|---|
| `file:guide.rst` | file node for guide.rst | absent | scanned RST file | Graph builder creates file nodes for each received `ParsedFile`, `graph_builder.py:121-135`; exact harness passes only parsed candidates at `test_wp6_g01_exact_semantics.py:196` | exact-test projection defect |
| `file:README.md` | file node for README.md | absent | scanned Markdown file | Same evidence | exact-test projection defect |
| `file:settings.toml` | file node for settings.toml | absent | scanned TOML file | Same evidence | exact-test projection defect |
| `test:tests/TestRoutes.py:test_greeting_service:4` | test node with `test:` key | actual node has `function:tests/TestRoutes.py:test_greeting_service:4` and kind `test` | `def test_greeting_service` at line 4 | Graph builder chooses `GraphNodeType.TEST` at `graph_builder.py:641-647` but uses raw `sym.symbol_id` at `:222-245`; parser builds that ID with `SymbolType.FUNCTION` at `python_ast.py:45-47` | production defect |
| `import:service/routes.py:fastapi:fastapi:1` | import node keyed by module twice | actual import node is keyed by imported name `FastAPI` | `from fastapi import FastAPI` at line 1 | Implementation uses `identity = imported_names[0]` at `graph_builder.py:298-311`; focused test `test_two_imports_same_module_same_line` requires imported names to distinguish nodes; docs describe a module-only ID | unresolved contract ambiguity |

All ordinary symbol nodes are common and field-identical: normalize_name,
fetch_profile, GreetingService, greet, _audit, get_profile, and
create_profile. Both route nodes are common and field-identical. Variables
are intentionally not graph nodes (`graph_builder.py:641-643` and
`test_variable_no_graph_node`).

```text
DOES_PRODUCTION_CREATE_FILE_NODES=True
DOES_PRODUCTION_CREATE_IMPORT_NODES=True
DOES_PRODUCTION_CREATE_TEST_KIND_NODES=True
DOES_PRODUCTION_USE_FUNCTION_KIND_FOR_TESTS=False
DOES_PRODUCTION_CREATE_ROUTE_NODES=True
GRAPH_NODE_MISMATCH_CLASSIFICATION=exact-test input-selection defect; production test-key defect; unresolved import-key contract
```

The file-node answer is qualified: the graph builder creates file nodes for
each `ParsedFile`, but the exact harness supplies only the four parsed Python
files. It does not create or receive the three non-Python file records.

## 8. Test graph-node kind adjudication

| Layer | Kind | Semantic key | Contract evidence |
|---|---|---|---|
| Parsed symbol | `function` | parser raw ID `function:tests/TestRoutes.py:test_greeting_service:4` | `SymbolType.FUNCTION`; `python_ast.py:45-47` assigns IDs from `symbol_type` |
| Manifest symbol | `function` | `test:tests:test_greeting_service` | Accepted manifest symbol record |
| Test record | test identity | `test:tests:test_greeting_service` | Exact harness test projection `:138-149` |
| Test chunk | `test` | `test:tests:test_greeting_service:4-5` | `chunker.py:208-210,230-237`; focused `test_test_function_chunk` |
| Graph node | `test` | actual `function:tests/TestRoutes.py:test_greeting_service:4` | `_symbol_to_node_type()` returns TEST, but graph node ID is raw `sym.symbol_id` |

```text
TEST_IS_PARSED_AS=function
TEST_IS_MANIFESTED_AS=function
TEST_CHUNK_TYPE=test
TEST_GRAPH_NODE_KIND=test
TEST_GRAPH_KEY_PREFIX=function (actual), test (expected)
TEST_GRAPH_MISMATCH_CLASSIFICATION=production defect in graph semantic-key construction
```

The graph node kind is already `test`; the mismatch is specifically the
semantic-key prefix. The exact projection preserves the raw node ID and does
not rewrite it. `tests/unit/test_graph_builder.py::test_test_symbol_ignored`
and `::test_tests_edge` establish test-node recognition/relationships, while
`docs/05_INDEXING_AND_RETRIEVAL.md` specifies `test:<qualified_name>` IDs.

## 9. Expected graph edges

| # | Source key | Target key | Edge type | Qualifier |
|---:|---|---|---|---|
| 1 | `file:service/helpers.py` | `function:service/helpers.py:normalize_name:4` | defines | — |
| 2 | `file:service/helpers.py` | `function:service/helpers.py:fetch_profile:8` | defines | — |
| 3 | `file:service/routes.py` | `class:service/routes.py:GreetingService:8` | defines | — |
| 4 | `file:service/routes.py` | `method:service/routes.py:greet:9` | defines | — |
| 5 | `file:service/routes.py` | `method:service/routes.py:_audit:12` | defines | — |
| 6 | `file:service/routes.py` | `function:service/routes.py:get_profile:17` | defines | — |
| 7 | `file:service/routes.py` | `function:service/routes.py:create_profile:22` | defines | — |
| 8 | `file:tests/TestRoutes.py` | `test:tests/TestRoutes.py:test_greeting_service:4` | defines | — |
| 9 | `class:service/routes.py:GreetingService:8` | `method:service/routes.py:greet:9` | defines | — |
| 10 | `class:service/routes.py:GreetingService:8` | `method:service/routes.py:_audit:12` | defines | — |
| 11 | `function:service/routes.py:get_profile:17` | `route:GET:/profiles/{user_id}:service/routes.py:16` | defines | — |
| 12 | `function:service/routes.py:create_profile:22` | `route:POST:/profiles:service/routes.py:21` | defines | — |
| 13 | `route:GET:/profiles/{user_id}:service/routes.py:16` | `function:service/routes.py:get_profile:17` | handles_route | — |
| 14 | `route:POST:/profiles:service/routes.py:21` | `function:service/routes.py:create_profile:22` | handles_route | — |
| 15 | `file:service/routes.py` | `import:service/routes.py:fastapi:fastapi:1` | imports | — |
| 16 | `file:service/routes.py` | `import:service/routes.py:helpers:DEFAULT_GREETING:3` | imports | — |
| 17 | `file:service/routes.py` | `import:service/routes.py:helpers:fetch_profile:3` | imports | — |
| 18 | `file:service/routes.py` | `import:service/routes.py:helpers:normalize_name:3` | imports | — |
| 19 | `method:service/routes.py:greet:9` | `function:service/helpers.py:normalize_name:4` | calls | — |
| 20 | `function:service/routes.py:get_profile:17` | `function:service/helpers.py:fetch_profile:8` | calls | — |
| 21 | `function:service/routes.py:create_profile:22` | `function:service/helpers.py:normalize_name:4` | calls | — |

## 10. Actual graph edges

| # | Source key | Target key | Edge type | Qualifier |
|---:|---|---|---|---|
| 1 | `function:service/routes.py:create_profile:22` | `function:service/helpers.py:normalize_name:4` | calls | — |
| 2 | `function:service/routes.py:get_profile:17` | `function:service/helpers.py:fetch_profile:8` | calls | — |
| 3 | `method:service/routes.py:greet:9` | `function:service/helpers.py:normalize_name:4` | calls | — |
| 4 | `file:service/helpers.py` | `function:service/helpers.py:normalize_name:4` | defines | — |
| 5 | `file:service/helpers.py` | `function:service/helpers.py:fetch_profile:8` | defines | — |
| 6 | `file:service/routes.py` | `import:service/routes.py:fastapi:FastAPI:1` | imports | — |
| 7 | `file:service/routes.py` | `method:service/routes.py:_audit:12` | defines | — |
| 8 | `function:service/routes.py:get_profile:17` | `route:GET:/profiles/{user_id}:service/routes.py:16` | defines | — |
| 9 | `route:GET:/profiles/{user_id}:service/routes.py:16` | `function:service/routes.py:get_profile:17` | handles_route | — |
| 10 | `file:service/routes.py` | `function:service/routes.py:get_profile:17` | defines | — |
| 11 | `function:service/routes.py:create_profile:22` | `route:POST:/profiles:service/routes.py:21` | defines | — |
| 12 | `route:POST:/profiles:service/routes.py:21` | `function:service/routes.py:create_profile:22` | handles_route | — |
| 13 | `file:service/routes.py` | `function:service/routes.py:create_profile:22` | defines | — |
| 14 | `file:service/routes.py` | `import:service/routes.py:helpers:DEFAULT_GREETING:3` | imports | — |
| 15 | `file:service/routes.py` | `import:service/routes.py:helpers:fetch_profile:3` | imports | — |
| 16 | `file:service/routes.py` | `import:service/routes.py:helpers:normalize_name:3` | imports | — |
| 17 | `file:service/routes.py` | `class:service/routes.py:GreetingService:8` | defines | — |
| 18 | `file:service/routes.py` | `method:service/routes.py:greet:9` | defines | — |
| 19 | `file:tests/TestRoutes.py` | `function:tests/TestRoutes.py:test_greeting_service:4` | defines | — |

The graph builder creates route `defines` edges from handler to route at
`graph_builder.py:173-193`, route `handles_route` edges at `:194-213`, file
defines edges at `:253-271`, import edges at `:324-348`, and calls edges at
`:544-587`.

## 11. Exact graph-edge differences

```text
MISSING_EXPECTED_GRAPH_EDGES=[
  (class:service/routes.py:GreetingService:8,
   method:service/routes.py:greet:9, defines, None),
  (class:service/routes.py:GreetingService:8,
   method:service/routes.py:_audit:12, defines, None),
  (file:tests/TestRoutes.py,
   test:tests/TestRoutes.py:test_greeting_service:4, defines, None),
  (file:service/routes.py,
   import:service/routes.py:fastapi:fastapi:1, imports, None)
]

UNEXPECTED_ACTUAL_GRAPH_EDGES=[
  (file:tests/TestRoutes.py,
   function:tests/TestRoutes.py:test_greeting_service:4, defines, None),
  (file:service/routes.py,
   import:service/routes.py:fastapi:FastAPI:1, imports, None)
]

COMMON_GRAPH_EDGES=17
DUPLICATE_ACTUAL_GRAPH_EDGES=[]
DANGLING_ACTUAL_EDGE_ENDPOINTS=[]
```

| Edge difference | Node-key dependent | Contract evidence | Classification |
|---|---|---|---|
| File-to-test `defines` | Yes; only the test node key changes | Graph builder emits a file-to-symbol edge using raw `node_id`; test node kind is already `test` | Production test-key defect, not an independent missing relationship |
| FastAPI `imports` edge | Yes; only the import node key changes | Graph builder uses imported name `FastAPI`; focused import-node tests require imported-name identity; docs and accepted oracle use a module-only-like key | Unresolved import-key contract ambiguity |
| Class-to-greet `defines` | No | Parser stores `parent=GreetingService` but leaves `parent_symbol_id=None`; graph builder adds parent edges only when `sym.parent_symbol_id` is truthy at `graph_builder.py:274-295`; docs require class-to-method definition relationships | Production parser/graph relationship defect |
| Class-to-_audit `defines` | No | Same parent-symbol evidence | Production parser/graph relationship defect |

The two route nodes and both route relationship pairs are present and
common. The three helper imports are present and common. The three calls are
present and common. Actual graph-builder invariants guarantee no dangling
endpoints, and the exact projection reports no duplicate canonical tuples.

```text
ACTUAL_DEFINES_EDGES=10
ACTUAL_HANDLES_ROUTE_EDGES=2
ACTUAL_IMPORTS_EDGES=4
ACTUAL_CALLS_EDGES=3
ACTUAL_OTHER_EDGES=0
ACTUAL_TOTAL_EDGES=19

EXPECTED_DEFINES_EDGES=12
EXPECTED_HANDLES_ROUTE_EDGES=2
EXPECTED_IMPORTS_EDGES=4
EXPECTED_CALLS_EDGES=3
EXPECTED_OTHER_EDGES=0
EXPECTED_TOTAL_EDGES=21
```

## 12. Three call edges

All three call edges exist in actual production graph output and match the
accepted canonical tuples:

- `GreetingService.greet -> normalize_name`: `method:service/routes.py:greet:9` → `function:service/helpers.py:normalize_name:4`, `calls`; match: yes.
- `get_profile -> fetch_profile`: `function:service/routes.py:get_profile:17` → `function:service/helpers.py:fetch_profile:8`, `calls`; match: yes.
- `create_profile -> normalize_name`: `function:service/routes.py:create_profile:22` → `function:service/helpers.py:normalize_name:4`, `calls`; match: yes.

The source calls are visible at routes.py lines 10, 18, and 23. The graph
builder extracts call names from parsed-symbol metadata at
`graph_builder.py:553-567` and finds the target symbols globally.

## 13. Classification matrix

| ID | Collection | Expected | Actual | Source evidence | Contract evidence | Classification | Required future correction |
|---|---|---|---|---|---|---|---|
| M1 | symbols | GreetingService end 14 | end 13 | Line 14 is blank; AST and `symbol_extractor.py` both end at 13 | AST `ClassDef.end_lineno` is the production boundary | manifest-oracle defect | Correct the source review and manifest class end to 13, then rerun exact comparison |
| M2 | chunks | class key/range `8-14` | `8-13` | Chunker copies symbol start/end | Class chunks inherit production symbol range | manifest-oracle defect | Correct the class chunk oracle to `8-13` after M1 |
| M3 | graph nodes | file nodes for guide.rst, README.md, settings.toml | absent | Exact harness calls `build(parsed)` with only four Python parse candidates at line 196 | Graph builder creates file nodes for every received ParsedFile; graph contract says every scanned file | exact-test projection defect | Supply complete graph input, including non-Python not-applicable file records, or document a deliberate exclusion |
| M4 | graph nodes | `import:...:fastapi:fastapi:1` | `import:...:fastapi:FastAPI:1` | `from fastapi import FastAPI` and raw graph builder identity use imported name | Focused import tests require imported-name uniqueness; docs specify module-only identity | unresolved contract ambiguity | Clarify import-node identity, then reconcile review/manifest and exact projection |
| M5 | graph nodes | `test:tests/TestRoutes.py:test_greeting_service:4` | `function:tests/TestRoutes.py:test_greeting_service:4`, kind test | Parser creates raw function-prefixed symbol ID; graph builder preserves it | Graph node branch sets kind test; docs specify `test:<qualified_name>` ID | production defect | Create a production graph semantic-key correction task; do not rewrite in the evidence test |
| M6 | graph edges | class→greet and class→_audit defines | both absent | Parser has `parent` but no `parent_symbol_id`; graph builder gates parent edges on `parent_symbol_id` | Docs require class-to-method definition relationships and parent symbol IDs | production defect | Create a parser/graph relationship correction task |
| M7 | graph edges | file→test defines with test key | file→test defines with function key | Same relationship exists under the raw actual node ID | Difference is entirely dependent on M5 | production defect, node-key dependent | Resolve M5, then regenerate the edge oracle |
| M8 | graph edges | file→fastapi:fastapi imports | file→fastapi:FastAPI imports | Same import relationship exists under the raw actual node ID | Difference is entirely dependent on M4 | unresolved contract ambiguity, node-key dependent | Resolve M4, then regenerate the edge oracle |

No independent mismatch was found for route nodes, route edges, ordinary
symbol nodes, helper import nodes, or the three call edges.

## 14. Minimal correction sequence

```text
ORACLE_CORRECTION_REQUIRED=True (M1 and M2; M4 only after contract decision)
PROJECTION_CORRECTION_REQUIRED=True (M3 graph input selection)
PRODUCTION_CORRECTION_REQUIRED=True (M5 and M6; review M3 against pipeline ownership)
CONTRACT_CLARIFICATION_REQUIRED=True (M4 import-node identity)
```

Recommended sequence, without implementing it here:

1. Correct the class range in the source-derived review and manifest from 14
   to 13; this corrects both M1 and M2.
2. Clarify whether the graph exact boundary must include every scanned file,
   including non-Python `not_applicable` files. If yes, correct the exact
   harness graph input and separately review the production orchestration
   boundary.
3. Clarify the import-node identity contract between the documentation,
   focused graph tests, implementation, and accepted oracle. Then update the
   chosen source review/manifest representation.
4. Create a separate production correction task for test graph semantic IDs
   (M5) and parent-symbol relationship extraction (M6); do not fix either in
   this evidence-only task.
5. Rerun the exact comparison, focused tests, and then the full suite only
   after the accepted oracle, projection, and production contracts are
   reconciled.

## 15. Verification

Focused command:

```text
python -m pytest -q tests/unit/test_python_ast.py tests/unit/test_symbol_extractor.py tests/unit/test_route_detector.py tests/unit/test_chunker.py tests/unit/test_graph_builder.py -ra
```

Result: `168 passed in 0.18s`, with zero skipped, xfailed, deselected, or
errors. The graph-builder identity/determinism tests are in
`tests/unit/test_graph_builder.py`; no separately named semantic-key test
file exists.

Exact comparison:

```text
1 failed, 2 passed in 0.13s
```

The exact comparison remains intentionally failing. No complete suite was
run. The evidence task did not invoke IndexService, persistence, Chroma,
embeddings, or CLI.

The fixture digest remains
`bba310f73070a23fb804cf5968ec0e530419ccb01ec056c86e1abec8bb44233c`, and no
fixture artifact was created.

## 16. Evidence-only conclusion

The class and class-chunk oracle values are contradicted by direct source and
AST evidence. The graph-node and graph-edge differences are not one single
defect: they comprise exact-harness graph-input selection, an import-key
contract ambiguity, a production test-key construction defect, and missing
parent-symbol relationship data. The accepted manifest, review, exact test,
and production code were not modified.
