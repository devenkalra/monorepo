"""Minimal bldrdojo MCP execution scaffold.

This module is transport-agnostic on purpose.
It focuses on tool discovery and tool execution against the REST backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json
import re

import requests


@dataclass
class SessionAuth:
    access: str | None = None
    refresh: str | None = None


@dataclass
class BldrdojoMcpServer:
    base_url: str = "http://localhost:8000"
    tools_file: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent.parent / "docs" / "api" / "tools.json"
    )
    timeout_seconds: int = 30
    _tool_map: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _sessions: dict[str, SessionAuth] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        manifest = json.loads(self.tools_file.read_text(encoding="utf-8"))
        self.base_url = manifest.get("server", {}).get("baseUrl", self.base_url)
        self._tool_map = {tool["name"]: tool for tool in manifest["tools"]}

    def list_tools(self) -> list[dict[str, Any]]:
        tools = self._virtual_tools() + [
            {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "inputSchema": tool.get("inputSchema", {"type": "object"}),
            }
            for tool in self._tool_map.values()
        ]
        return tools

    @staticmethod
    def _virtual_tools() -> list[dict[str, Any]]:
        return [
            {
                "name": "search_entities",
                "description": "Resolve a user-provided name/query to matching entity identifiers.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Name or partial name to find."},
                        "type": {"type": "string", "description": "Optional entity type filter, e.g. Person."},
                        "page_size": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "get_entity_neighborhood",
                "description": "Fetch a deterministic neighborhood snapshot for an entity (outgoing relationships).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "Exact entity identifier."},
                        "max_neighbors": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
                    },
                    "required": ["entity_id"],
                    "additionalProperties": False,
                },
            },
        ]

    def describe_tool_call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return planned MCP/backend request metadata for debugging/observability."""
        args = arguments or {}
        if name == "search_entities":
            query = str(args.get("query", "")).strip()
            page_size = args.get("page_size", 10)
            internal_args: dict[str, Any] = {"search": query, "page_size": page_size}
            if args.get("type"):
                internal_args["type"] = args["type"]
            return {
                "ok": True,
                "mcp_tool": name,
                "virtual": True,
                "internal_calls": [
                    {
                        "tool": "entities.list",
                        "arguments": internal_args,
                        "backend": {
                            "method": "GET",
                            "path": "/api/entities/",
                            "url": f"{self.base_url}/api/entities/",
                            "query": internal_args,
                        },
                    }
                ],
            }
        if name == "get_entity_neighborhood":
            entity_id = args.get("entity_id") or args.get("id")
            return {
                "ok": True,
                "mcp_tool": name,
                "virtual": True,
                "internal_calls": [
                    {
                        "tool": "entities.llm_context",
                        "arguments": {"id": entity_id},
                        "backend": {
                            "method": "GET",
                            "path": f"/api/entities/{entity_id}/llm_context/",
                            "url": f"{self.base_url}/api/entities/{entity_id}/llm_context/",
                        },
                    },
                ],
            }

        spec = self._tool_map.get(name)
        if not spec:
            return {
                "ok": False,
                "error": {
                    "code": "NOT_FOUND",
                    "message": f"Unknown tool: {name}",
                },
            }

        backend = spec["backend"]
        method = backend["method"].upper()
        path = self._format_path(backend["path"], args)
        params: dict[str, Any] = {}
        payload: dict[str, Any] | None = None

        if method == "GET":
            params = self._clean_query_params(name, args)
        elif method in {"POST", "PATCH", "PUT"}:
            payload = args.get("payload") if "payload" in args else self._clean_body_params(name, args)

        return {
            "ok": True,
            "mcp_tool": name,
            "backend": {
                "method": method,
                "path": path,
                "url": f"{self.base_url}{path}",
                "query": params,
                "json": payload,
            },
        }

    def set_session_auth(self, session_id: str, access: str | None, refresh: str | None = None) -> None:
        existing = self._sessions.get(session_id, SessionAuth())
        existing.access = access
        # Preserve an existing refresh token when caller does not provide one.
        if refresh is not None:
            existing.refresh = refresh
        self._sessions[session_id] = existing

    def has_session_auth(self, session_id: str) -> bool:
        auth = self._sessions.get(session_id)
        return bool(auth and auth.access)

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None, session_id: str = "default") -> dict[str, Any]:
        args = arguments or {}
        if name == "search_entities":
            return self._call_search_entities(args=args, session_id=session_id)
        if name == "get_entity_neighborhood":
            return self._call_get_entity_neighborhood(args=args, session_id=session_id)

        spec = self._tool_map.get(name)
        if not spec:
            return self._error("NOT_FOUND", f"Unknown tool: {name}", 404)

        backend = spec["backend"]
        method = backend["method"].upper()
        path = self._format_path(backend["path"], args)

        try:
            if name == "auth.login":
                return self._handle_login(path, args, session_id)
            if name == "auth.refresh":
                return self._handle_refresh(path, args, session_id)

            return self._proxy_request(name, method, path, args, session_id)
        except requests.Timeout:
            return self._error("TIMEOUT", "Upstream request timed out", 504)
        except requests.RequestException as exc:
            return self._error("UPSTREAM_ERROR", f"Request failed: {exc}", 502)
        except Exception as exc:  # pragma: no cover - defensive
            return self._error("INTERNAL", str(exc), 500)

    def _proxy_request(
        self,
        tool_name: str,
        method: str,
        path: str,
        args: dict[str, Any],
        session_id: str,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        auth = self._sessions.get(session_id)
        if auth and auth.access:
            headers["Authorization"] = f"Bearer {auth.access}"

        url = f"{self.base_url}{path}"
        params: dict[str, Any] = {}
        payload: dict[str, Any] | None = None

        if method == "GET":
            params = self._clean_query_params(tool_name, args)
        elif method in {"POST", "PATCH", "PUT"}:
            payload = args.get("payload") if "payload" in args else self._clean_body_params(tool_name, args)

        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params if params else None,
            json=payload,
            timeout=self.timeout_seconds,
        )

        if response.status_code == 401 and auth and auth.refresh:
            refreshed = self._attempt_auto_refresh(session_id)
            if refreshed:
                headers["Authorization"] = f"Bearer {self._sessions[session_id].access}"
                response = requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params if params else None,
                    json=payload,
                    timeout=self.timeout_seconds,
                )

        if not response.ok:
            return self._error(
                self._map_error_code(response.status_code),
                self._extract_error_message(response),
                response.status_code,
                {
                    "response": self._safe_json(response),
                    "backend_call": {
                        "method": method,
                        "path": path,
                        "url": url,
                        "query": params,
                        "json": payload,
                        "status_code": response.status_code,
                    },
                },
            )

        data = self._safe_json(response)

        # Relationship views should only expose outgoing edges to avoid symmetric duplicates.
        if tool_name == "entities.relations":
            data = self._outgoing_relations_only(data)

        # MeiliSearch can be stale; for name-based lookups, fall back to DB-backed entities list.
        if tool_name == "search.query" and self._should_fallback_search_query(data, args):
            fallback = self._fallback_search_via_entities(headers=headers, args=args)
            if fallback is not None:
                return {
                    "ok": True,
                    "data": fallback,
                    "meta": {"fallback": "entities.list"},
                }

        return {
            "ok": True,
            "data": data,
            "meta": {
                "backend_call": {
                    "method": method,
                    "path": path,
                    "url": url,
                    "query": params,
                    "json": payload,
                    "status_code": response.status_code,
                }
            },
        }

    @staticmethod
    def _should_fallback_search_query(data: Any, args: dict[str, Any]) -> bool:
        if not isinstance(data, dict):
            return False
        if not args.get("q"):
            return False
        try:
            count = int(data.get("count", 0))
        except (TypeError, ValueError):
            return False
        return count == 0

    def _fallback_search_via_entities(self, headers: dict[str, str], args: dict[str, Any]) -> dict[str, Any] | None:
        params: dict[str, Any] = {
            "search": args.get("q", ""),
        }
        if args.get("type"):
            params["type"] = args["type"]

        # Keep pagination behavior aligned with search.query arguments.
        page = args.get("page")
        page_size = args.get("page_size")
        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["page_size"] = page_size

        try:
            response = requests.get(
                f"{self.base_url}/api/entities/",
                headers=headers,
                params=params,
                timeout=self.timeout_seconds,
            )
            if not response.ok:
                return None
            payload = self._safe_json(response)
            if not isinstance(payload, dict):
                return None

            count = payload.get("count", 0)
            results = payload.get("results", [])
            if page is None:
                page = 1
            if page_size is None:
                page_size = 20
            try:
                page_i = int(page)
            except (TypeError, ValueError):
                page_i = 1
            try:
                page_size_i = int(page_size)
            except (TypeError, ValueError):
                page_size_i = 20
            total_pages = (int(count) + page_size_i - 1) // page_size_i if page_size_i > 0 else 0

            return {
                "results": results,
                "count": count,
                "page": page_i,
                "page_size": page_size_i,
                "total_pages": total_pages,
            }
        except requests.RequestException:
            return None

    def _call_search_entities(self, args: dict[str, Any], session_id: str) -> dict[str, Any]:
        query = str(args.get("query", "")).strip()
        if not query:
            return self._error("VALIDATION_ERROR", "query is required", 400)

        page_size_raw = args.get("page_size", 10)
        try:
            page_size = int(page_size_raw)
        except (TypeError, ValueError):
            page_size = 10
        page_size = max(1, min(page_size, 50))

        requested_type = args.get("type")
        candidate_queries = self._candidate_entity_queries(query)

        payload: dict[str, Any] = {}
        results: list[dict[str, Any]] = []
        used_query = query
        last_error: dict[str, Any] | None = None
        internal_calls: list[dict[str, Any]] = []

        for candidate in candidate_queries:
            search_args: dict[str, Any] = {"search": candidate, "page_size": page_size}
            if requested_type:
                search_args["type"] = requested_type

            listing = self.call_tool("entities.list", arguments=search_args, session_id=session_id)
            listing_meta = listing.get("meta") if isinstance(listing, dict) else None
            backend_call = listing_meta.get("backend_call") if isinstance(listing_meta, dict) else None
            internal_calls.append(
                {
                    "tool": "entities.list",
                    "arguments": search_args,
                    "backend_call": backend_call,
                    "ok": bool(listing.get("ok")) if isinstance(listing, dict) else False,
                }
            )
            if not listing.get("ok"):
                last_error = listing
                continue

            candidate_payload = listing.get("data", {})
            candidate_results = candidate_payload.get("results", []) if isinstance(candidate_payload, dict) else []
            payload = candidate_payload if isinstance(candidate_payload, dict) else {}
            used_query = candidate
            if candidate_results:
                results = candidate_results
                break

        if not results and last_error is not None and not payload:
            return last_error

        matches: list[dict[str, Any]] = []
        for row in results:
            if not isinstance(row, dict):
                continue
            matches.append(
                {
                    "entity_id": row.get("id"),
                    "label": row.get("type"),
                    "name": row.get("display"),
                }
            )

        return {
            "ok": True,
            "data": {
                "query": query,
                "used_query": used_query,
                "matches": matches,
                "count": payload.get("count", len(matches)) if isinstance(payload, dict) else len(matches),
            },
            "meta": {
                "internal_calls": internal_calls,
            },
        }

    @staticmethod
    def _candidate_entity_queries(query: str) -> list[str]:
        q = query.strip()
        if not q:
            return []

        candidates: list[str] = [q]
        patterns = [
            r"^\s*tell\s+me\s+about\s+(.+?)\s*[?.!]*\s*$",
            r"^\s*what\s+do\s+you\s+know\s+about\s+(.+?)\s*[?.!]*\s*$",
            r"^\s*who\s+is\s+(.+?)\s*[?.!]*\s*$",
            r"^\s*find\s+(.+?)\s*[?.!]*\s*$",
            r"^\s*details\s+about\s+(.+?)\s*[?.!]*\s*$",
            r"^\s*info(?:rmation)?\s+about\s+(.+?)\s*[?.!]*\s*$",
        ]
        for pattern in patterns:
            m = re.match(pattern, q, flags=re.IGNORECASE)
            if m:
                extracted = m.group(1).strip()
                if extracted:
                    candidates.append(extracted)

        # Last-resort fallback: strip punctuation and collapse whitespace.
        simplified = re.sub(r"[^\w\s-]", " ", q)
        simplified = re.sub(r"\s+", " ", simplified).strip()
        if simplified and simplified not in candidates:
            candidates.append(simplified)

        # Dedupe while preserving order.
        deduped: list[str] = []
        for item in candidates:
            if item not in deduped:
                deduped.append(item)
        return deduped

    def _call_get_entity_neighborhood(self, args: dict[str, Any], session_id: str) -> dict[str, Any]:
        entity_id = str(args.get("entity_id") or args.get("id") or "").strip()
        if not entity_id:
            return self._error("VALIDATION_ERROR", "entity_id is required", 400)

        max_neighbors_raw = args.get("max_neighbors", 50)
        try:
            max_neighbors = int(max_neighbors_raw)
        except (TypeError, ValueError):
            max_neighbors = 50
        max_neighbors = max(1, min(max_neighbors, 200))

        headers = {"Accept": "application/json"}
        auth = self._sessions.get(session_id)
        if auth and auth.access:
            headers["Authorization"] = f"Bearer {auth.access}"

        try:
            context_resp = requests.get(
                f"{self.base_url}/api/entities/{entity_id}/llm_context/",
                headers=headers,
                timeout=self.timeout_seconds,
            )
            if context_resp.ok:
                payload = self._safe_json(context_resp)
                if isinstance(payload, dict):
                    text_block = payload.get("text_block") if isinstance(payload.get("text_block"), str) else ""
                    return {
                        "ok": True,
                        "data": {
                            "text": text_block,
                        },
                    }
        except requests.RequestException:
            pass

        entity_resp = self.call_tool("entities.get", arguments={"id": entity_id}, session_id=session_id)
        if not entity_resp.get("ok"):
            return entity_resp

        rel_resp = self.call_tool("entities.relations", arguments={"id": entity_id}, session_id=session_id)
        if not rel_resp.get("ok"):
            return rel_resp

        entity = entity_resp.get("data", {}) if isinstance(entity_resp.get("data"), dict) else {}
        rel_payload = rel_resp.get("data", {}) if isinstance(rel_resp.get("data"), dict) else {}
        outgoing = rel_payload.get("outgoing", []) if isinstance(rel_payload.get("outgoing"), list) else []
        outgoing = outgoing[:max_neighbors]

        triples: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        relationship_lines: list[str] = []

        subject_name = entity.get("display") or entity_id
        subject_type = entity.get("type") or "Entity"

        for rel in outgoing:
            if not isinstance(rel, dict):
                continue
            relation_type = str(rel.get("relation_type", "")).strip().upper()
            neighbor = rel.get("entity", {}) if isinstance(rel.get("entity"), dict) else {}
            neighbor_id = neighbor.get("id")
            neighbor_name = neighbor.get("display") or str(neighbor_id or "Unknown")
            neighbor_type = neighbor.get("type") or "Entity"

            triples.append(
                {
                    "subject_id": entity_id,
                    "subject_name": subject_name,
                    "predicate": relation_type,
                    "object_id": neighbor_id,
                    "object_name": neighbor_name,
                    "object_type": neighbor_type,
                }
            )
            relationships.append(
                {
                    "relation_type": relation_type,
                    "entity": {
                        "id": neighbor_id,
                        "name": neighbor_name,
                        "type": neighbor_type,
                    },
                }
            )
            relationship_lines.append(f"  - {relation_type} -> {neighbor_type}: {neighbor_name}")

        text_lines = [
            f"Entity: {subject_name} (Type: {subject_type})",
            "Properties:",
            f"  - description: {entity.get('description', '')}",
            "Relationships:",
        ]
        if relationship_lines:
            text_lines.extend(relationship_lines)
        else:
            text_lines.append("  - (no outgoing relationships found)")

        return {
            "ok": True,
            "data": {
                "entity": {
                    "id": entity.get("id", entity_id),
                    "name": subject_name,
                    "type": subject_type,
                    "description": entity.get("description", ""),
                },
                "relationships": relationships,
                "triples": triples,
                "text": "\n".join(text_lines),
            },
        }

    def _handle_login(self, path: str, args: dict[str, Any], session_id: str) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        response = requests.post(url, json=args, timeout=self.timeout_seconds)
        if not response.ok:
            return self._error(
                self._map_error_code(response.status_code),
                self._extract_error_message(response),
                response.status_code,
                self._safe_json(response),
            )

        data = self._safe_json(response)
        self._sessions[session_id] = SessionAuth(
            access=data.get("access"),
            refresh=data.get("refresh"),
        )
        return {"ok": True, "data": data}

    def _handle_refresh(self, path: str, args: dict[str, Any], session_id: str) -> dict[str, Any]:
        refresh = args.get("refresh")
        if not refresh:
            existing = self._sessions.get(session_id)
            refresh = existing.refresh if existing else None
        if not refresh:
            return self._error("VALIDATION_ERROR", "refresh token is required", 400)

        url = f"{self.base_url}{path}"
        response = requests.post(url, json={"refresh": refresh}, timeout=self.timeout_seconds)
        if not response.ok:
            return self._error(
                self._map_error_code(response.status_code),
                self._extract_error_message(response),
                response.status_code,
                self._safe_json(response),
            )

        data = self._safe_json(response)
        session = self._sessions.get(session_id, SessionAuth())
        session.access = data.get("access")
        session.refresh = refresh
        self._sessions[session_id] = session
        return {"ok": True, "data": data}

    def _attempt_auto_refresh(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if not session or not session.refresh:
            return False
        refresh_response = self.call_tool("auth.refresh", {"refresh": session.refresh}, session_id=session_id)
        return bool(refresh_response.get("ok"))

    @staticmethod
    def _format_path(path_template: str, args: dict[str, Any]) -> str:
        path = path_template
        for key, value in args.items():
            token = "{" + key + "}"
            if token in path:
                path = path.replace(token, str(value))
        return path

    @staticmethod
    def _clean_query_params(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        excluded = {"id", "task_id", "payload", "parameters", "debug", "refresh", "email", "password"}
        out = {k: v for k, v in args.items() if k not in excluded and v is not None}
        if tool_name == "mail.emails.list" and "has_attachments" in out:
            out["has_attachments"] = str(bool(out["has_attachments"])).lower()
        return out

    @staticmethod
    def _clean_body_params(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "cad.render":
            return {
                "parameters": args.get("parameters", {}),
                "debug": bool(args.get("debug", False)),
            }
        return {k: v for k, v in args.items() if k not in {"id", "task_id"}}

    @staticmethod
    def _safe_json(response: requests.Response) -> Any:
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            try:
                return response.json()
            except ValueError:
                return {"raw": response.text}
        return {"raw": response.text}

    @staticmethod
    def _outgoing_relations_only(data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "outgoing" not in data and "incoming" not in data:
            return data

        filtered = dict(data)
        outgoing = filtered.get("outgoing", [])
        filtered["outgoing"] = outgoing if isinstance(outgoing, list) else []
        filtered["incoming"] = []
        return filtered

    @staticmethod
    def _extract_error_message(response: requests.Response) -> str:
        data = BldrdojoMcpServer._safe_json(response)
        if isinstance(data, dict):
            for key in ("detail", "error", "message"):
                value = data.get(key)
                if isinstance(value, str) and value:
                    return value
        return f"HTTP {response.status_code}"

    @staticmethod
    def _map_error_code(status_code: int) -> str:
        if status_code == 400:
            return "VALIDATION_ERROR"
        if status_code == 401:
            return "AUTH_REQUIRED"
        if status_code == 404:
            return "NOT_FOUND"
        if status_code == 409:
            return "CONFLICT"
        if 500 <= status_code <= 599:
            return "UPSTREAM_ERROR"
        return "UPSTREAM_ERROR"

    @staticmethod
    def _error(code: str, message: str, status: int, details: Any | None = None) -> dict[str, Any]:
        return {
            "ok": False,
            "error": {
                "code": code,
                "message": message,
                "status": status,
                "details": details or {},
            },
        }


if __name__ == "__main__":
    server = BldrdojoMcpServer()
    print(json.dumps({"tools": server.list_tools()}, indent=2))
