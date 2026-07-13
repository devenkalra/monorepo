from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from .llm.openai_responses import OpenAIResponsesPlanner
from .llm.planner import RuleBasedPlanner
from .mcp_server import MCPServerRuntime
from .repository.backend_api import BackendAPIGraphRepository

import requests


class _SessionAuth:
    def __init__(self, access: str | None = None, refresh: str | None = None) -> None:
        self.access = access
        self.refresh = refresh


class _QAJob:
    def __init__(self, question: str, model: str, planner_name: str) -> None:
        self.job_id = str(uuid4())
        self.question = question
        self.model = model
        self.planner = planner_name
        self.status = "running"
        self.created_at = time.time()
        self.updated_at = self.created_at
        self.answer = ""
        self.trace: list[dict[str, Any]] = []
        self.status_events: list[dict[str, Any]] = []
        self.entities: list[str] = []
        self.facts: list[str] = []
        self.error: str | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "answer": self.answer,
            "trace": self.trace,
            "status_events": self.status_events,
            "entities": self.entities,
            "facts": self.facts,
            "planner": self.planner,
            "error": self.error,
            "updated_at": self.updated_at,
        }


def _normalize_backend_base_url(url: str) -> str:
    base = (url or "").strip().rstrip("/")
    if base.endswith("/api"):
        return base[: -len("/api")]
    return base


def _read_dotenv_value(key: str) -> str | None:
    candidates = [
        Path(__file__).resolve().parents[3] / "data-backend" / ".env",
        Path(__file__).resolve().parents[2] / ".env",
    ]
    for env_path in candidates:
        if not env_path.exists():
            continue
        try:
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export ") :].strip()
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() != key:
                    continue
                value = v.strip().strip('"').strip("'")
                return value or None
        except OSError:
            continue
    return None


def _resolve_openai_api_key(request_api_key: str) -> str | None:
    if request_api_key:
        return request_api_key
    env_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if env_key:
        return env_key
    return _read_dotenv_value("OPENAI_API_KEY")


def _load_frontend_html() -> bytes:
    html_path = Path(__file__).resolve().parents[2] / "prompt_frontend.html"
    html = html_path.read_text(encoding="utf-8")
    return html.encode("utf-8")


class PromptWebHandler(BaseHTTPRequestHandler):
    backend_base_url: str
    default_model: str
    html: bytes
    sessions: dict[str, _SessionAuth]
    qa_jobs: dict[str, _QAJob]
    qa_jobs_lock: threading.Lock

    def _backend_get(self, path: str, timeout: int = 30, access: str | None = None) -> requests.Response:
        headers = {"Accept": "application/json"}
        if access:
            headers["Authorization"] = f"Bearer {access}"
        return requests.get(f"{self.backend_base_url}{path}", headers=headers, timeout=timeout)

    def _backend_post(self, path: str, payload: dict[str, Any], timeout: int = 30) -> requests.Response:
        return requests.post(f"{self.backend_base_url}{path}", json=payload, timeout=timeout)

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send_bytes(200, self.html, "text/html; charset=utf-8")
            return
        if self.path == "/api/version":
            self._send_json(
                200,
                {
                    "ok": True,
                    "data": {
                        "service": "mcp2-web",
                        "version": "0.1.0",
                        "backend_base_url": self.backend_base_url,
                    },
                },
            )
            return
        if self.path == "/api/google/config":
            try:
                resp = self._backend_get("/api/auth/google/url/")
                data = resp.json() if "application/json" in resp.headers.get("Content-Type", "") else {"raw": resp.text}
                if not resp.ok:
                    self._send_json(502, {"ok": False, "error": {"message": "Google config fetch failed", "details": data}})
                    return
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "data": {
                            "client_id": data.get("client_id"),
                            "redirect_uri": data.get("redirect_uri"),
                            "scope": "openid profile email",
                        },
                    },
                )
            except requests.RequestException as exc:
                self._send_json(502, {"ok": False, "error": {"message": f"Backend network error: {exc}"}})
            return
        if self.path.startswith("/api/auth/status"):
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            session_id = (qs.get("session_id", ["web-default"])[0] or "web-default").strip()
            auth = self.sessions.get(session_id)
            authenticated = bool(auth and auth.access)

            entities_count: int | None = None
            if authenticated and auth and auth.access:
                try:
                    count_resp = self._backend_get("/api/entities/?page_size=1", access=auth.access)
                    if count_resp.ok:
                        payload = count_resp.json() if "application/json" in count_resp.headers.get("Content-Type", "") else {}
                        if isinstance(payload, dict) and isinstance(payload.get("count"), int):
                            entities_count = payload.get("count")
                except requests.RequestException:
                    authenticated = False

            self._send_json(
                200,
                {
                    "ok": True,
                    "data": {
                        "authenticated": authenticated,
                        "entities_count": entities_count,
                    },
                },
            )
            return
        if self.path.startswith("/api/qa/status"):
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            job_id = (qs.get("job_id", [""])[0] or "").strip()
            if not job_id:
                self._send_json(400, {"ok": False, "error": {"message": "job_id is required"}})
                return
            with self.qa_jobs_lock:
                job = self.qa_jobs.get(job_id)
                if not job:
                    self._send_json(404, {"ok": False, "error": {"message": "Unknown job_id"}})
                    return
                data = job.snapshot()
            self._send_json(200, {"ok": True, "data": data})
            return
        self._send_json(404, {"ok": False, "error": {"message": "Not found"}})

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._set_common_headers("application/json; charset=utf-8", 0)
        self.end_headers()

    def do_POST(self) -> None:
        if self.path == "/api/google/exchange":
            try:
                payload = self._read_json_body()
            except ValueError as exc:
                self._send_json(400, {"ok": False, "error": {"message": str(exc)}})
                return

            access_token = str(payload.get("access_token", "")).strip()
            session_id = str(payload.get("session_id", "web-default")).strip() or "web-default"
            if not access_token:
                self._send_json(400, {"ok": False, "error": {"message": "access_token is required"}})
                return

            try:
                resp = self._backend_post("/api/auth/google/", {"access_token": access_token}, timeout=60)
                data = resp.json() if "application/json" in resp.headers.get("Content-Type", "") else {"raw": resp.text}
                if not resp.ok:
                    self._send_json(502, {"ok": False, "error": {"message": "Google exchange failed", "details": data}})
                    return
                jwt_access = data.get("access")
                jwt_refresh = data.get("refresh")
                if not jwt_access:
                    self._send_json(502, {"ok": False, "error": {"message": "Google exchange did not return JWT access token", "details": data}})
                    return

                self.sessions[session_id] = _SessionAuth(access=jwt_access, refresh=jwt_refresh)
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "data": {
                            "session_id": session_id,
                            "authenticated": True,
                            "user": data.get("user") or data.get("user_details") or {},
                        },
                    },
                )
            except requests.RequestException as exc:
                self._send_json(502, {"ok": False, "error": {"message": f"Backend network error: {exc}"}})
            return

        if self.path != "/api/qa":
            self._send_json(404, {"ok": False, "error": {"message": "Not found"}})
            return

        try:
            payload = self._read_json_body()
        except ValueError as exc:
            self._send_json(400, {"ok": False, "error": {"message": str(exc)}})
            return

        question = str(payload.get("question", "")).strip()
        request_api_key = str(payload.get("api_key", "")).strip()
        api_key = _resolve_openai_api_key(request_api_key)
        model = str(payload.get("model", self.default_model)).strip() or self.default_model
        session_id = str(payload.get("session_id", "web-default")).strip() or "web-default"

        if not question:
            self._send_json(400, {"ok": False, "error": {"message": "question is required"}})
            return

        try:
            auth = self.sessions.get(session_id)
            repo = BackendAPIGraphRepository(
                base_url=self.backend_base_url,
                access_token=auth.access if auth else None,
            )
            runtime = MCPServerRuntime(repo)
            if api_key:
                planner = OpenAIResponsesPlanner(api_key=api_key, model=model)
            else:
                planner = RuleBasedPlanner()

            job = _QAJob(question=question, model=model, planner_name=planner.__class__.__name__)
            with self.qa_jobs_lock:
                self.qa_jobs[job.job_id] = job

            def _worker() -> None:
                def _on_trace(event: dict[str, Any]) -> None:
                    with self.qa_jobs_lock:
                        j = self.qa_jobs.get(job.job_id)
                        if not j:
                            return
                        j.trace.append(event)
                        if isinstance(event.get("NEW_E"), list):
                            for item in event["NEW_E"]:
                                if item not in j.entities:
                                    j.entities.append(item)
                        if isinstance(event.get("NEW_F"), list):
                            for item in event["NEW_F"]:
                                if item not in j.facts:
                                    j.facts.append(item)
                        j.updated_at = time.time()

                def _on_status(event: dict[str, Any]) -> None:
                    with self.qa_jobs_lock:
                        j = self.qa_jobs.get(job.job_id)
                        if not j:
                            return
                        j.status_events.append(event)
                        j.updated_at = time.time()

                try:
                    repo.set_status_callback(_on_status)
                    _on_status({"phase": "init", "message": "Job started"})
                    result = asyncio.run(
                        runtime.controller.run_question(
                            question=question,
                            planner=planner,
                            on_trace_event=_on_trace,
                            on_status_event=_on_status,
                        )
                    )
                    with self.qa_jobs_lock:
                        j = self.qa_jobs.get(job.job_id)
                        if not j:
                            return
                        j.answer = result.answer
                        j.entities = result.entities
                        j.facts = result.facts
                        j.trace = result.trace
                        j.status_events.append({"phase": "complete", "message": "Job completed"})
                        j.status = "completed"
                        j.updated_at = time.time()
                except Exception as exc:  # pragma: no cover
                    with self.qa_jobs_lock:
                        j = self.qa_jobs.get(job.job_id)
                        if not j:
                            return
                        j.status_events.append({"phase": "error", "message": f"Job failed: {exc}"})
                        j.status = "failed"
                        j.error = str(exc)
                        j.updated_at = time.time()
                finally:
                    repo.set_status_callback(None)

            threading.Thread(target=_worker, daemon=True).start()

            self._send_json(
                202,
                {
                    "ok": True,
                    "data": {
                        "job_id": job.job_id,
                        "status": "running",
                        "planner": planner.__class__.__name__,
                    },
                },
            )
        except Exception as exc:  # pragma: no cover
            self._send_json(500, {"ok": False, "error": {"message": str(exc)}})

    def _read_json_body(self) -> dict[str, Any]:
        length_header = self.headers.get("Content-Length")
        if not length_header:
            raise ValueError("Missing Content-Length")
        length = int(length_header)
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc
        if not isinstance(body, dict):
            raise ValueError("JSON body must be an object")
        return body

    def _send_json(self, status_code: int, obj: dict[str, Any]) -> None:
        data = json.dumps(obj, ensure_ascii=True).encode("utf-8")
        self._send_bytes(status_code, data, "application/json; charset=utf-8")

    def _send_bytes(self, status_code: int, data: bytes, content_type: str) -> None:
        try:
            self.send_response(status_code)
            self._set_common_headers(content_type, len(data))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            # Client disconnected before the response was fully written.
            return

    def _set_common_headers(self, content_type: str, content_length: int) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(content_length))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def log_message(self, format_str: str, *args: Any) -> None:
        return


def run_web_server(
    runtime: MCPServerRuntime,
    host: str = "127.0.0.1",
    port: int = 8787,
    default_model: str = "gpt-4.1-mini",
    backend_base_url: str = "https://bldrdojo.com/api/",
) -> None:
    _ = runtime
    PromptWebHandler.backend_base_url = _normalize_backend_base_url(backend_base_url)
    PromptWebHandler.default_model = default_model
    PromptWebHandler.html = _load_frontend_html()
    PromptWebHandler.sessions = {}
    PromptWebHandler.qa_jobs = {}
    PromptWebHandler.qa_jobs_lock = threading.Lock()

    server = ThreadingHTTPServer((host, port), PromptWebHandler)
    print(f"mcp2 web server listening on http://{host}:{port}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
