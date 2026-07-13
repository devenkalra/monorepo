# bldrdojo MCP Server Scaffold

This folder contains a minimal MCP server scaffold for the bldrdojo data backend.

## What is included

- `server.py`: a lightweight tool dispatcher that reads `docs/api/tools.json` and proxies requests to the backend API.
- `transport_stdio.py`: MCP-style JSON-RPC stdio transport (`initialize`, `tools/list`, `tools/call`, `ping`).
- `__main__.py`: module entrypoint to run the stdio server.
- Session-level token storage (in-memory) for `auth.login` and authenticated tool calls.
- Normalized `{ok, data}` and `{ok, error}` responses.

## Current status

This scaffold now includes a working stdio transport compatible with MCP-style
JSON-RPC message flow.

It is suitable for local integration and iterative tool development.

## Run a quick smoke test

From `data-backend`:

```powershell
python -c "from mcp_server.server import BldrdojoMcpServer; s=BldrdojoMcpServer(); print(s.list_tools()[:3])"
```

Run stdio server:

```powershell
python -m mcp_server
```

The process expects framed JSON-RPC over stdin/stdout using `Content-Length` headers.

## Run the Prompt Frontend

This starts a local web UI that:

- takes a prompt and LLM API key,
- calls an LLM service,
- executes tool calls through `BldrdojoMcpServer`.

From `data-backend`:

```powershell
python -m mcp_server.prompt_frontend
```

Open:

- `http://127.0.0.1:8787`

Optional env vars:

- `PROMPT_FRONTEND_HOST` (default `127.0.0.1`)
- `PROMPT_FRONTEND_PORT` (default `8787`)
- `PROMPT_FRONTEND_MODEL` (default `gpt-4.1-mini`)
- `OPENAI_CHAT_COMPLETIONS_URL` (default `https://api.openai.com/v1/chat/completions`)

## Next implementation steps

1. Persist auth/session state beyond process memory if needed.
2. Add file upload/download tool handlers (`import/export` tools) when needed.
3. Add destructive-action confirmation gates for tools like `entities.delete` and `search.delete_all`.
4. Add HTTP transport variant if your MCP client does not use stdio.
