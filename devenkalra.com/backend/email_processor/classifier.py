"""OpenAI structured classification + alias bypass routing."""

from __future__ import annotations

import json
import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)

INTENTS = (
    'writing_idea',
    'image_ingest',
    'newsletter',
    'receipt',
    'ignore',
    'unknown',
)

CLASSIFICATION_SCHEMA = {
    'name': 'email_classification',
    'strict': True,
    'schema': {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'intent': {'type': 'string', 'enum': list(INTENTS)},
            'confidence': {'type': 'number'},
            'summary': {'type': 'string'},
            'reason': {'type': 'string'},
            'extracted': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {
                    'title': {'type': 'string'},
                    'urls': {'type': 'array', 'items': {'type': 'string'}},
                    'tags': {'type': 'array', 'items': {'type': 'string'}},
                    'is_newsletter': {'type': 'boolean'},
                    'is_automated': {'type': 'boolean'},
                    'has_images': {'type': 'boolean'},
                    'sender_role': {
                        'type': 'string',
                        'enum': ['person', 'company', 'noreply', 'unknown'],
                    },
                },
                'required': [
                    'title', 'urls', 'tags', 'is_newsletter',
                    'is_automated', 'has_images', 'sender_role',
                ],
            },
            'suggested_actions': {
                'type': 'array',
                'items': {'type': 'string'},
            },
            'risk_flags': {
                'type': 'array',
                'items': {'type': 'string'},
            },
        },
        'required': [
            'intent', 'confidence', 'summary', 'reason',
            'extracted', 'suggested_actions', 'risk_flags',
        ],
    },
}

SYSTEM_PROMPT = """You classify inbound personal emails for automation.
Pick exactly one intent:
- writing_idea: idea, note, or research to save as a Creative ClickUp task
- image_ingest: email whose main value is photos/images to keep
- newsletter: marketing digests, subscriptions, bulk lists
- receipt: orders, invoices, shipping, account confirmations
- ignore: noise (social notifications, CI noise, spam-adjacent)
- unknown: ambiguous or important personal mail

Never recommend deleting personal or financial mail. Only newsletters are bulk-safe.
Return confidence 0-1. Flag risk_flags like possible_personal, possible_financial, attachment_present when relevant.
"""


def parse_alias_routes():
    """
    EMAIL_ALIAS_ROUTES=writing_idea@kalra.com:writing_idea,images@kalra.com:image_ingest
    """
    raw = getattr(settings, 'EMAIL_ALIAS_ROUTES', '') or ''
    routes = {}
    for part in raw.split(','):
        part = part.strip()
        if not part or ':' not in part:
            continue
        addr, intent = part.split(':', 1)
        addr = addr.strip().lower()
        intent = intent.strip()
        if addr and intent in INTENTS:
            routes[addr] = intent
    return routes


def extract_recipient_addresses(to_field, headers=None):
    headers = headers or {}
    blobs = [to_field or '']
    for key in ('delivered-to', 'x-original-to', 'x-forwarded-to'):
        if headers.get(key):
            blobs.append(headers[key])
    found = []
    for blob in blobs:
        for match in re.findall(r'[\w.+\-]+@[\w.\-]+\.\w+', blob.lower()):
            if match not in found:
                found.append(match)
    return found


def bypass_intent_for_recipients(recipients):
    routes = parse_alias_routes()
    for addr in recipients:
        if addr in routes:
            return routes[addr]
    return None


def classify_with_openai(*, subject, from_address, to_addresses, snippet, body_text):
    from openai import OpenAI

    api_key = getattr(settings, 'EMAIL_OPENAI_API_KEY', '') or getattr(settings, 'OPENAI_API_KEY', '')
    model = getattr(settings, 'EMAIL_OPENAI_MODEL', 'gpt-4.1-mini')
    if not api_key:
        raise RuntimeError('EMAIL_OPENAI_API_KEY (or OPENAI_API_KEY) is not configured')

    client = OpenAI(api_key=api_key)
    user_content = (
        f"From: {from_address}\n"
        f"To: {to_addresses}\n"
        f"Subject: {subject}\n"
        f"Snippet: {snippet}\n\n"
        f"Body (truncated):\n{(body_text or '')[:6000]}"
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': user_content},
        ],
        response_format={
            'type': 'json_schema',
            'json_schema': CLASSIFICATION_SCHEMA,
        },
        temperature=0.1,
    )
    content = resp.choices[0].message.content
    data = json.loads(content)
    data['model'] = model
    data['confidence'] = float(data.get('confidence') or 0)
    if data.get('intent') not in INTENTS:
        data['intent'] = 'unknown'
    return data


def should_auto_run(classification):
    threshold = float(getattr(settings, 'EMAIL_CONFIDENCE_AUTO', 0.85))
    intent = classification.get('intent')
    confidence = float(classification.get('confidence') or 0)
    risk = set(classification.get('risk_flags') or [])
    if intent in ('unknown', 'receipt'):
        return False
    if risk & {'possible_personal', 'possible_financial'}:
        return False
    if confidence < threshold:
        return False
    return intent in ('writing_idea', 'image_ingest', 'ignore', 'newsletter')


def workflow_kind_for_intent(intent):
    mapping = {
        'writing_idea': 'writing_idea',
        'image_ingest': 'image_ingest',
        'ignore': 'ignore',
        'newsletter': 'newsletter',
    }
    return mapping.get(intent)
