"""LocalAI-first LLM client with OpenAI fallback + process packing."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import requests
from django.conf import settings

from .models import CATEGORIES

logger = logging.getLogger(__name__)

_CHARS_PER_TOKEN = 3
_RESPONSE_RESERVE_TOKENS = 2048
_OVERHEAD_TOKENS = 512
_CONTEXT_AVAILABLE_RE = re.compile(
    r'available context size\s*\((\d+)\s*tokens?\)',
    re.IGNORECASE,
)


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
        getattr(settings, 'GMAIL_OPENAI_MODEL', '')
        or os.environ.get('GMAIL_OPENAI_MODEL', '')
        or 'gpt-4o-mini'
    )


def _localai_model() -> str:
    return (
        getattr(settings, 'GMAIL_LOCALAI_MODEL', '')
        or os.environ.get('GMAIL_LOCALAI_MODEL', '')
        or 'qwen3-32b'
    )


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)


def parse_available_context(error_text: str) -> int | None:
    match = _CONTEXT_AVAILABLE_RE.search(error_text or '')
    if not match:
        return None
    return max(1024, int(match.group(1)))


def chat_completion(
    *,
    prompt: str,
    system: str,
    json_mode: bool = False,
    timeout: float = 600.0,
) -> str:
    """Try LocalAI, then OpenAI. Returns assistant content string."""
    errors: list[str] = []
    local_url = _localai_url()
    if local_url:
        model = _localai_model()
        endpoint = f'{local_url}/v1/chat/completions'
        logger.info('LLM request provider=localai model=%s url=%s', model, endpoint)
        try:
            content = _post_chat(
                url=endpoint,
                api_key=_localai_key(),
                model=model,
                prompt=prompt,
                system=system,
                json_mode=json_mode,
                timeout=timeout,
            )
            logger.info('LLM success provider=localai model=%s', model)
            return content
        except Exception as exc:  # noqa: BLE001
            logger.warning('LocalAI chat failed: %s', exc)
            errors.append(f'localai: {exc}')

    openai_key = _openai_key()
    if not openai_key:
        raise RuntimeError(
            'LLM failed'
            + (f' ({"; ".join(errors)})' if errors else '')
            + ' and OPENAI_API_KEY is not set'
        )
    model = _openai_model()
    logger.info('LLM request provider=openai model=%s', model)
    content = _post_chat(
        url='https://api.openai.com/v1/chat/completions',
        api_key=openai_key,
        model=model,
        prompt=prompt,
        system=system,
        json_mode=json_mode,
        timeout=timeout,
    )
    logger.info('LLM success provider=openai model=%s', model)
    return content


def _post_chat(
    *,
    url: str,
    api_key: str,
    model: str,
    prompt: str,
    system: str,
    json_mode: bool,
    timeout: float,
) -> str:
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    payload: dict[str, Any] = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': prompt},
        ],
        'temperature': 0.1,
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
    content = data['choices'][0]['message'].get('content') or ''
    return str(content).strip()


def summarize_email_text(body_block: str) -> dict[str, Any]:
    cats = ', '.join(CATEGORIES)
    system = (
        'You classify and summarize emails. Reply with JSON only. '
        'Do not invent facts not present in the email.'
    )
    prompt = (
        'Summarize and classify this email. Return JSON with keys: '
        'brief_summary (string), key_points (array of strings), details (string), '
        f'category (one of: {cats}), category_confidence (0-1 number).\n\n'
        f'{body_block}'
    )
    # Prefer recording whichever endpoint is configured first; chat_completion
    # logs the actual provider used (LocalAI vs OpenAI fallback).
    used_model = _localai_model() if _localai_url() else _openai_model()
    raw = chat_completion(prompt=prompt, system=system, json_mode=True)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        fence = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw, re.I)
        data = json.loads(fence.group(1)) if fence else {}
    category = str(data.get('category') or 'Other')
    if category not in CATEGORIES:
        category = 'Other'
    conf = float(data.get('category_confidence') or 0)
    conf = max(0.0, min(1.0, conf))
    points = data.get('key_points') or []
    if not isinstance(points, list):
        points = [str(points)]
    return {
        'brief_summary': str(data.get('brief_summary') or '').strip(),
        'key_points': [str(p).strip() for p in points if str(p).strip()],
        'details': str(data.get('details') or '').strip(),
        'category': category,
        'category_confidence': conf,
        'model': used_model,
    }


def format_email_block(message: dict[str, Any], index: int) -> str:
    body = (message.get('body_text') or message.get('snippet') or '').strip()
    return (
        f'===== Email {index} =====\n'
        f"From: {message.get('from_addr') or ''}\n"
        f"Subject: {message.get('subject') or ''}\n"
        f"Date: {message.get('date_iso') or ''}\n\n"
        f'{body}\n'
    )


def pack_batches(blocks: list[str], budget_tokens: int) -> list[list[str]]:
    budget_chars = max(0, budget_tokens * _CHARS_PER_TOKEN)
    batches: list[list[str]] = []
    current: list[str] = []
    used = 0
    for block in blocks:
        need = len(block) + (8 if current else 0)
        if current and used + need > budget_chars:
            batches.append(current)
            current = []
            used = 0
            need = len(block)
        if need > budget_chars:
            truncated = block[: max(0, budget_chars - 20)].rstrip() + '\n…[truncated]\n'
            batches.append([truncated])
            continue
        current.append(block)
        used += need
    if current:
        batches.append(current)
    return batches


def run_process_prompt(
    *,
    user_prompt: str,
    messages: list[dict[str, Any]],
    context_size: int,
    on_progress=None,
) -> str:
    context_size = max(1024, min(64000, int(context_size or 8192)))
    prompt_tokens = estimate_tokens(user_prompt) + _OVERHEAD_TOKENS
    budget = max(512, context_size - _RESPONSE_RESERVE_TOKENS - prompt_tokens)
    blocks = [format_email_block(m, i) for i, m in enumerate(messages, start=1)]
    system = (
        'You analyze one or more emails for the user. '
        'Follow their instructions carefully. '
        'Do not invent facts that are not in the emails. '
        'Reply in clear plain text or markdown.'
    )
    pending = list(blocks)
    batch_results: list[str] = []
    batch_num = 0
    repacks = 0
    while pending:
        batches = pack_batches(pending, budget)
        batch = batches[0]
        rest = [b for group in batches[1:] for b in group]
        batch_num += 1
        combined = '\n'.join(batch)
        llm_prompt = (
            f'{user_prompt.strip()}\n\n'
            'Use only information present in the emails below. '
            'If something is not mentioned, say so.\n'
        )
        if rest or len(batches) > 1:
            llm_prompt += (
                f'This is batch {batch_num}. Answer for this batch only.\n\n'
            )
        llm_prompt += f'--- EMAILS ({len(batch)}) ---\n\n{combined}'
        if on_progress:
            on_progress(
                {
                    'phase': 'processing',
                    'message': f'Batch {batch_num} · {len(batch)} email(s)',
                    'batch': batch_num,
                }
            )
        try:
            text = chat_completion(
                prompt=llm_prompt, system=system, json_mode=False
            )
            batch_results.append(text)
            pending = rest
        except Exception as exc:  # noqa: BLE001
            live = parse_available_context(str(exc))
            if live and live < context_size and repacks < 4:
                repacks += 1
                context_size = live
                budget = max(
                    512, context_size - _RESPONSE_RESERVE_TOKENS - prompt_tokens
                )
                batch_num -= 1
                if on_progress:
                    on_progress(
                        {
                            'phase': 'repack',
                            'message': f'Repacking for context {live}',
                        }
                    )
                continue
            raise

    if len(batch_results) == 1:
        return batch_results[0]
    merged = '\n\n'.join(
        f'### Batch {i}\n\n{t}' for i, t in enumerate(batch_results, start=1)
    )
    if estimate_tokens(merged) <= budget:
        if on_progress:
            on_progress({'phase': 'merging', 'message': 'Merging batch answers…'})
        return chat_completion(
            prompt=(
                f'The user asked:\n{user_prompt}\n\n'
                'Merge these batch answers into one coherent final answer. '
                'Deduplicate. Do not invent facts.\n\n'
                f'{merged}'
            ),
            system='Merge partial email answers. Do not invent facts.',
            json_mode=False,
        )
    return merged
