# mcp2

Iterative question answering MCP server over a general knowledge graph.

## Highlights
- Query-local alias mapping (`p1`, `o1`, `l1`, etc.) with UUID stability per cycle.
- Generic graph retrieval tools:
  - `get_entities`
  - `traverse_relation`
- Iterative LLM controller with OpenAI Responses API support.
- Per-query deduplication of entities, facts, traversals, and fetches.
- Compact KG schema + triple serialization.
- Optional rebase/compaction support for long loops.
- Unit tests for sibling reasoning, traversal discovery, name collisions, org reasoning, unsupported derived relations, and duplicate expansion.

## Quick start
```bash
cd mcp2
python -m pip install -e .[test]
pytest -q
```

## Run demo server
```bash
cd mcp2
python -m mcp2.main
```

By default this runs with an in-memory repository. Replace the repository implementation to connect Neo4j/PostgreSQL/other backends.

## Run interactive web frontend
```bash
cd mcp2
MCP2_MODE=web python -m mcp2.main
```

On Windows PowerShell:
```powershell
Set-Location "c:\code\monorepo\mcp2"
$env:MCP2_MODE = "web"
C:/Users/deven/AppData/Local/Python/pythoncore-3.14-64/python.exe -m mcp2.main
```

Then open:
- `http://127.0.0.1:8787/`

Optional backend target override:
```powershell
$env:MCP2_BACKEND_BASE_URL = "http://127.0.0.1:8000"
```

The web mode integrates Google sign-in with the data-backend endpoints:
- `GET /api/google/config` (proxies backend `/api/auth/google/url/`)
- `POST /api/google/exchange` (proxies backend `/api/auth/google/`)
- `GET /api/auth/status?session_id=...`

The frontend posts to:
- `POST /api/qa`

Payload shape:
```json
{
  "question": "Who is Riya's sister?",
  "model": "gpt-4.1-mini",
  "api_key": "optional"
}
```
