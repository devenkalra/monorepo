"""LocalAI-first chat client with OpenAI fallback."""

from __future__ import annotations

import os
from typing import Any

import requests
from django.conf import settings


def _localai_url() -> str:
    return (
        getattr(settings, 'LOCALAI_URL', '')
        or os.environ.get('LOCALAI_URL', '')
        or ''
    ).rstrip('/')


def _localai_key() -> str:
    return (
        getattr(settings, 'LOCALAI_API_KEY', '')
        or os.environ.get('LOCALAI_API_KEY', '')
        or ''
    )


def _openai_key() -> str:
    return (
        getattr(settings, 'OPENAI_API_KEY', '')
        or os.environ.get('OPENAI_API_KEY', '')
        or ''
    )


def _openai_model() -> str:
    return (
        os.environ.get('PRODUCTIONS_OPENAI_MODEL', '')
        or getattr(settings, 'GMAIL_OPENAI_MODEL', '')
        or os.environ.get('GMAIL_OPENAI_MODEL', '')
        or 'gpt-4o-mini'
    )


def _localai_model() -> str:
    return (
        os.environ.get('PRODUCTIONS_LOCALAI_MODEL', '')
        or getattr(settings, 'GMAIL_LOCALAI_MODEL', '')
        or os.environ.get('GMAIL_LOCALAI_MODEL', '')
        or 'qwen3-32b'
    )


def llm_available() -> bool:
    return bool(_localai_url() or _openai_key())


def chat_completion(*, prompt: str, system: str, json_mode: bool = True, timeout: float = 90.0, temperature: float = 0.4) -> str:
    errors: list[str] = []
    local_url = _localai_url()
    if local_url:
        try:
            return _post_chat(
                url=f'{local_url}/v1/chat/completions',
                api_key=_localai_key(),
                model=_localai_model(),
                prompt=prompt,
                system=system,
                json_mode=json_mode,
                timeout=timeout,
                temperature=temperature,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f'localai: {exc}')

    openai_key = _openai_key()
    if not openai_key:
        raise RuntimeError(
            'No LLM configured. Set OPENAI_API_KEY or LOCALAI_URL.'
            + (f' ({"; ".join(errors)})' if errors else '')
        )
    return _post_chat(
        url='https://api.openai.com/v1/chat/completions',
        api_key=openai_key,
        model=_openai_model(),
        prompt=prompt,
        system=system,
        json_mode=json_mode,
        timeout=timeout,
        temperature=temperature,
    )


def _post_chat(*, url: str, api_key: str, model: str, prompt: str, system: str, json_mode: bool, timeout: float, temperature: float = 0.4) -> str:
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    payload: dict[str, Any] = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': prompt},
        ],
        'temperature': temperature,
    }
    if json_mode:
        payload['response_format'] = {'type': 'json_object'}
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code >= 400 and json_mode:
        payload.pop('response_format', None)
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f'chat failed ({resp.status_code}): {resp.text[:500]}')
    data = resp.json()
    return str(data['choices'][0]['message'].get('content') or '').strip()
