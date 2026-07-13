from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
from datetime import datetime
from contextlib import contextmanager
import json
import inspect
import os
from pathlib import Path

import requests


@dataclass
class LoginResult:
    status_code: int
    body: Dict[str, Any]


class E2EApiClient:
    _shared_log_file_path: Optional[Path] = None

    def __init__(self, base_url: str, timeout_seconds: int = 20):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self._request_counter = 0
        self._subtest_phrase: Optional[str] = None
        self._call_purpose: Optional[str] = None
        log_file = os.environ.get("E2E_API_LOG_FILE", "tests/integration/e2e/e2e_api_calls.md")
        if self.__class__._shared_log_file_path is None:
            self.__class__._shared_log_file_path = self._build_timestamped_log_path(log_file)
            self._log_owner = True
        else:
            self._log_owner = False

        self.log_file_path = self.__class__._shared_log_file_path
        self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
        if self._log_owner:
            self._start_log_run()

    def set_subtest_phrase(self, phrase: Optional[str]) -> None:
        self._subtest_phrase = (phrase or "").strip() or None

    @contextmanager
    def log_call_purpose(self, purpose: Optional[str]):
        prev = self._call_purpose
        self._call_purpose = (purpose or "").strip() or None
        try:
            yield
        finally:
            self._call_purpose = prev

    @staticmethod
    def _build_timestamped_log_path(log_file: str) -> Path:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        raw_path = Path(log_file)

        # If caller provides an explicit extension, keep the same directory and extension,
        # but add timestamp to filename for per-run log isolation.
        if raw_path.suffix:
            return raw_path.with_name(f"{raw_path.stem}_{timestamp}{raw_path.suffix}")

        raw_path_str = str(log_file)
        is_dir_like = raw_path_str.endswith("/") or raw_path_str.endswith("\\")
        if is_dir_like or (raw_path.exists() and raw_path.is_dir()):
            return raw_path / f"e2e_api_calls_{timestamp}.md"

        # If no extension and not clearly a directory, treat input as a filename prefix.
        return raw_path.with_name(f"{raw_path.name}_{timestamp}.md")

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def _auth_headers(self) -> Dict[str, str]:
        if not self.access_token:
            return {}
        return {"Authorization": f"Bearer {self.access_token}"}

    @staticmethod
    def _mask_headers(headers: Dict[str, Any]) -> Dict[str, Any]:
        masked = dict(headers or {})
        auth_val = masked.get("Authorization")
        if isinstance(auth_val, str) and auth_val:
            if auth_val.startswith("Bearer "):
                token = auth_val[len("Bearer "):]
                if len(token) > 10:
                    masked["Authorization"] = f"Bearer {token[:6]}...{token[-4:]}"
                else:
                    masked["Authorization"] = "Bearer ***"
            else:
                masked["Authorization"] = "***"
        return masked

    @staticmethod
    def _mask_payload(payload: Any) -> Any:
        if not isinstance(payload, dict):
            return payload
        masked = {}
        sensitive = {"password", "password1", "password2", "access", "refresh", "token", "key"}
        for k, v in payload.items():
            masked[k] = "***" if str(k).lower() in sensitive else v
        return masked

    @staticmethod
    def _safe_json_dumps(value: Any) -> str:
        try:
            return json.dumps(value, indent=2, ensure_ascii=True, default=str)
        except Exception:
            return str(value)

    @staticmethod
    def _response_body_preview(response, max_chars: int = 3000) -> str:
        try:
            body_obj = response.json() if response.content else {}
            text = json.dumps(body_obj, indent=2, ensure_ascii=True, default=str)
        except ValueError:
            text = response.text or ""
        if len(text) > max_chars:
            return text[:max_chars] + "\n... [truncated]"
        return text

    def _append_log(self, text: str) -> None:
        with self.log_file_path.open("a", encoding="utf-8") as f:
            f.write(text)

    def finalize_test_outcome(self, test_function: str, failed: bool) -> None:
        """Tag all log entry titles for a test method with [FAIL] when it fails."""
        if not test_function:
            return
        if not self.log_file_path.exists():
            return

        try:
            original = self.log_file_path.read_text(encoding="utf-8")
        except OSError:
            return

        had_trailing_newline = original.endswith("\n")
        lines = original.splitlines()
        changed = False

        for i, line in enumerate(lines):
            if line.strip() != f"- Test: {test_function}":
                continue

            # Walk backward to find this entry title line.
            title_idx = -1
            for j in range(i - 1, -1, -1):
                if lines[j].startswith("### "):
                    title_idx = j
                    break
            if title_idx < 0:
                continue

            title = lines[title_idx][4:]
            clean = title
            if clean.startswith("[FAIL] "):
                clean = clean[len("[FAIL] "):]
            elif clean.startswith("[PASS] "):
                clean = clean[len("[PASS] "):]

            new_title = f"[FAIL] {clean}" if failed else clean
            new_line = f"### {new_title}"
            if lines[title_idx] != new_line:
                lines[title_idx] = new_line
                changed = True

        if changed:
            updated = "\n".join(lines)
            if had_trailing_newline:
                updated += "\n"
            try:
                self.log_file_path.write_text(updated, encoding="utf-8")
            except OSError:
                return

    def _start_log_run(self) -> None:
        started_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        self._append_log(
            "\n\n---\n"
            f"## E2E API Log\n"
            f"- Start: {started_at}\n"
            f"- Base: {self.base_url}\n"
            f"- File: {self.log_file_path.as_posix()}\n"
            "\n"
        )

    @staticmethod
    def _parse_doc_metadata(doc: str) -> Dict[str, str]:
        meta: Dict[str, str] = {}
        if not doc:
            return meta
        for raw_line in doc.splitlines():
            line = raw_line.strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip().lower().replace(" ", "_")
            value = value.strip()
            if key and value:
                meta[key] = value
        return meta

    @classmethod
    def _detect_test_context(cls) -> Dict[str, Any]:
        # Find the nearest unittest method on the stack and extract metadata from docstring.
        # Supported context methods: test_*, setUpClass, setUp, tearDownClass, tearDown.
        context = {
            "function": "unknown_test",
            "log_title": "Test Unknown",
            "meta": {},
        }
        context_names = {"setUpClass", "setUp", "tearDownClass", "tearDown"}
        for frame_info in inspect.stack():
            fn_name = frame_info.function
            if not isinstance(fn_name, str):
                continue
            if not (fn_name.startswith("test_") or fn_name in context_names):
                continue

            method_obj = None
            loc = frame_info.frame.f_locals
            if "self" in loc:
                method_obj = getattr(loc["self"].__class__, fn_name, None)
            elif "cls" in loc:
                method_obj = getattr(loc["cls"], fn_name, None)

            doc = inspect.getdoc(method_obj) if method_obj else ""
            meta = cls._parse_doc_metadata(doc or "")
            title = meta.get("log_title") or meta.get("title") or fn_name
            context.update(
                {
                    "function": fn_name,
                    "log_title": title,
                    "meta": meta,
                }
            )
            return context

        return context

    def _log_markdown_io(
        self,
        req_id: int,
        method: str,
        path: str,
        url: str,
        req_headers: Dict[str, Any],
        req_payload: Any,
        response,
        test_context: Dict[str, Any],
    ) -> None:
        context_meta = test_context.get("meta", {}) or {}
        context_function = test_context.get("function", "unknown_test")
        context_title = test_context.get("log_title", context_function)
        if self._subtest_phrase:
            context_title = f"{context_title} - {self._subtest_phrase}"
        if self._call_purpose:
            context_title = f"{context_title} - {self._call_purpose}"

        optional_meta_lines = []
        for key in ["feature", "scenario", "objective", "id"]:
            if key in context_meta:
                label = key.capitalize()
                optional_meta_lines.append(f"- {label}: {context_meta[key]}\n")
        if self._subtest_phrase:
            optional_meta_lines.append(f"- Sub: {self._subtest_phrase}\n")
        if self._call_purpose:
            optional_meta_lines.append(f"- Action: {self._call_purpose}\n")

        entry = (
            f"### {context_title}\n\n"
            f"- Test: {context_function}\n"
            + "".join(optional_meta_lines)
            + "\n"
            "#### Req\n"
            f"- Call: {req_id}\n"
            f"- Verb: {method}\n"
            f"- Path: {path}\n"
            f"- Url: {url}\n"
            "- Headers:\n"
            "```json\n"
            f"{self._safe_json_dumps(self._mask_headers(req_headers))}\n"
            "```\n"
            "- Body:\n"
            "```json\n"
            f"{self._safe_json_dumps(self._mask_payload(req_payload))}\n"
            "```\n"
            "#### Res\n"
            f"- Status: {response.status_code}\n"
            "- Body:\n"
            "```json\n"
            f"{self._response_body_preview(response)}\n"
            "```\n\n"
        )
        self._append_log(entry)

    def _request(self, method: str, path: str, *, add_auth: bool = True, **kwargs):
        headers = kwargs.pop("headers", {})
        if add_auth:
            headers = {**headers, **self._auth_headers()}

        url = self._url(path)
        request_payload = kwargs.get("json")
        if request_payload is None:
            request_payload = kwargs.get("data")

        response = self.session.request(
            method=method,
            url=url,
            headers=headers,
            timeout=self.timeout_seconds,
            **kwargs,
        )
        test_context = self._detect_test_context()

        self._request_counter += 1
        self._log_markdown_io(
            req_id=self._request_counter,
            method=method.upper(),
            path=path,
            url=url,
            req_headers=headers,
            req_payload=request_payload,
            response=response,
            test_context=test_context,
        )
        return response

    def get(self, path: str, **kwargs):
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs):
        return self._request("POST", path, **kwargs)

    def patch(self, path: str, **kwargs):
        return self._request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs):
        return self._request("DELETE", path, **kwargs)

    @staticmethod
    def json_or_empty(response) -> Dict[str, Any]:
        try:
            return response.json() if response.content else {}
        except ValueError:
            return {}

    def login(self, email: str, password: str) -> LoginResult:
        payload = {"email": email, "password": password}
        response = self._request("POST", "/api/auth/login/", add_auth=False, json=payload)

        body: Dict[str, Any]
        try:
            body = response.json() if response.content else {}
        except ValueError:
            body = {}

        # dj-rest-auth can return one of:
        # 1) {"access": "...", "refresh": "..."}
        # 2) {"key": "..."}
        self.access_token = body.get("access") or body.get("key")
        self.refresh_token = body.get("refresh")

        return LoginResult(status_code=response.status_code, body=body)

    def logout(self):
        return self.post("/api/auth/logout/")

    def token_refresh(self):
        if not self.refresh_token:
            return None
        response = self._request(
            "POST",
            "/api/auth/token/refresh/",
            add_auth=False,
            json={"refresh": self.refresh_token},
        )
        if response.ok:
            try:
                body = response.json()
            except ValueError:
                body = {}
            if "access" in body:
                self.access_token = body["access"]
        return response
