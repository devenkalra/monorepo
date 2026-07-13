"""Prompt frontend that uses an LLM service and the bldrdojo MCP server.

This starts a small local web app:
- Serves a chat-like prompt UI
- Calls an LLM service (OpenAI Chat Completions API)
- Executes tool calls via BldrdojoMcpServer

Run:
    python -m mcp_server.prompt_frontend
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
import json
import os
import re
from mcp.server.fastmcp import FastMCP

import requests

try:
    from mcp_server.server import BldrdojoMcpServer
except ModuleNotFoundError:
    # Support direct execution from inside the mcp_server directory.
    from server import BldrdojoMcpServer


HOST = os.environ.get("PROMPT_FRONTEND_HOST", "127.0.0.1")
PORT = int(os.environ.get("PROMPT_FRONTEND_PORT", "8787"))
DEFAULT_MODEL = os.environ.get("PROMPT_FRONTEND_MODEL", "gpt-4.1-mini")
OPENAI_URL = os.environ.get("OPENAI_CHAT_COMPLETIONS_URL", "https://api.openai.com/v1/chat/completions")
FRONTEND_VERSION = "0.4.1"


def _read_dotenv_value(key: str) -> str | None:
    """Read a single key from data-backend/.env without extra dependencies."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return None

    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() != key:
                continue
            value = v.strip().strip('"').strip("'")
            return value or None
    except OSError:
        return None

    return None


def _resolve_openai_api_key(request_api_key: str) -> str | None:
    if request_api_key:
        return request_api_key
    env_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if env_key:
        return env_key
    return _read_dotenv_value("OPENAI_API_KEY")


def _backend_get(path: str, timeout: int = 30) -> requests.Response:
    mcp = PromptFrontendHandler.mcp_server
    return requests.get(f"{mcp.base_url}{path}", timeout=timeout)


def _backend_post(path: str, payload: dict[str, Any], timeout: int = 30) -> requests.Response:
    mcp = PromptFrontendHandler.mcp_server
    return requests.post(f"{mcp.base_url}{path}", json=payload, timeout=timeout)


def _load_html() -> bytes:
    html_path = Path(__file__).with_name("prompt_frontend.html")
    html = html_path.read_text(encoding="utf-8")
    return html.replace("__FRONTEND_VERSION__", FRONTEND_VERSION).encode("utf-8")


def _safe_tool_name(name: str) -> str:
    # OpenAI function tool names must match ^[a-zA-Z0-9_-]+$.
    return name.replace(".", "_")


def _to_openai_tools(mcp_tools: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    out: list[dict[str, Any]] = []
    safe_to_original: dict[str, str] = {}

    for tool in mcp_tools:
        original_name = tool["name"]
        safe_name = _safe_tool_name(original_name)
        # Ensure uniqueness if multiple names collapse to same safe token.
        suffix = 2
        unique_name = safe_name
        while unique_name in safe_to_original and safe_to_original[unique_name] != original_name:
            unique_name = f"{safe_name}_{suffix}"
            suffix += 1

        safe_to_original[unique_name] = original_name
        out.append(
            {
                "type": "function",
                "function": {
                    "name": unique_name,
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {"type": "object"}),
                },
            }
        )
    return out, safe_to_original


def _openai_chat(api_key: str, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0.2,
    }
    response = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()


def _cleanup_answer_with_llm(api_key: str, model: str, user_prompt: str, raw_text: str) -> str:
    cleaned_source = (raw_text or "").strip()
    if not cleaned_source:
        return cleaned_source

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You rewrite structured factual notes into concise natural prose. "
                    "Keep every fact accurate and do not add new facts. "
                    "Avoid repetitive sentence starts and repetitive subject mentions. "
                    "Use 1 short paragraph, then optionally a second sentence if needed. "
                    "Do not include raw JSON/dict/list dumps, file paths, or media URLs."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"User request: {user_prompt}\n\n"
                    f"Factual source text:\n{cleaned_source}\n\n"
                    "Rewrite naturally while preserving facts exactly."
                ),
            },
        ],
        "temperature": 0.2,
    }

    response = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    raw = response.json()
    choice = raw.get("choices", [{}])[0]
    message = choice.get("message", {}) if isinstance(choice, dict) else {}
    content = message.get("content") if isinstance(message, dict) else ""
    cleaned = str(content or "").strip()
    return cleaned or cleaned_source

system_prompt1 = """
Answer the question below or identify the relevant entities in the given text that you need more information.  
Identify proper nouns in the text as entities needed to answer the question. 
Return as JSON object 
{answer: "", actual answer, entities_needed: [array of strings]}'
Return ONLY valid JSON with no markdown. Do not include relation words like child, parent, spouse, wife, "
"husband, or verbs.

When detecting entities, follow the following rules.
- Include explicitly named people, organizations, places, and other named entities.
- Also include family names, surnames, group names, or collective references when they identify a set of entities, even when used in plural form.
- Normalize plural family references to the base family name. For example:
"Who are siblings among the Kalras?" → ["Kalra"]
"Which of the Smiths work at Google?" → ["Smith"].
- If you normalize plural family references, ensure you return the base family name as well as the plural one.
"Who is the child of Deven Kalra and Nidhi Kalra?" → ["Deven Kalra", "Nidhi Kalra"]
- Do not include relationship words such as "sibling", "child", "parent", or "spouse" as entities.
- Do not infer entities that are not mentioned in the question.

When answering the question follow the following rules:
- Understand the natural-language meaning of the question, including implicit constraints.
- Generate possible candidate answers from the context.
- Before answering, verify each candidate against every constraint implied by the question.
- A candidate must satisfy all constraints, not merely the main relationship.
- Explicit facts in the context override assumptions and linguistic defaults.
- Reject any candidate for whom the context explicitly contradicts a required constraint.
- Do not change or weaken the meaning of a relationship term merely to produce an answer.
-If no candidate satisfies all required constraints, say that the answer cannot be determined from the provided context.

Examples of semantic constraints:

"sister" requires a sibling relationship and female gender
"brother" requires a sibling relationship and male gender
"daughter" requires a child relationship and female gender
"son" requires a child relationship and male gender

These examples illustrate the principle only. Apply the same semantic reasoning to other relationship terms and constraints without requiring an exhaustive predefined list.

"""

system_prompt = """
You are answering questions using information retrieved iteratively from a knowledge graph.

At each step, decide whether:

You can answer the question from the current context.
You need information about one or more known entities.
You need to expand a relationship from a known entity to discover additional connected entities.

Do not answer "unknown" merely because the current context does not yet contain a matching answer.

Before answering "unknown", consider whether additional graph retrieval could discover relevant candidates.

Important principles:

Interpret the user's natural language semantically.
Identify the exact requested relationship and all implied constraints.
Find possible reasoning paths through the graph.
Request additional information when an unresolved graph path could materially affect the answer.
An entity lookup returns information about a known entity.
A relationship expansion discovers entities connected through a specified graph relationship.
Use relationship expansion when the identity of the needed entity is not yet known.
Do not request unrelated entities merely because they appear in the context.
Answer only when the available information is sufficient, or when no useful unresolved retrieval path remains.

Return exactly one JSON object in one of these forms:

{
"action": "fetch_entities",
"entities": ["Entity Name"]
}

{
"action": "expand_relation",
"entity": "Entity Name",
"relationship": "relationship_name",
"direction": "incoming | outgoing | either"
}

{
"action": "answer",
"answer": "Final answer"
}


Identify proper nouns in the text as entities needed to answer the question. 
Return as JSON object 
{answer: "", actual answer, entities_needed: [array of strings]}'
Return ONLY valid JSON with no markdown. Do not include relation words like child, parent, spouse, wife, "
"husband, or verbs.

When detecting entities, follow the following rules.
- Include explicitly named people, organizations, places, and other named entities.
- Also include family names, surnames, group names, or collective references when they identify a set of entities, even when used in plural form.
- Normalize plural family references to the base family name. For example:
"Who are siblings among the Kalras?" → ["Kalra"]
"Which of the Smiths work at Google?" → ["Smith"].
- If you normalize plural family references, ensure you return the base family name as well as the plural one.
"Who is the child of Deven Kalra and Nidhi Kalra?" → ["Deven Kalra", "Nidhi Kalra"]
- Do not include relationship words such as "sibling", "child", "parent", or "spouse" as entities.
- Do not infer entities that are not mentioned in the question.

When answering the question follow the following rules:
- Understand the natural-language meaning of the question, including implicit constraints.
- Generate possible candidate answers from the context.
- Before answering, verify each candidate against every constraint implied by the question.
- A candidate must satisfy all constraints, not merely the main relationship.
- Explicit facts in the context override assumptions and linguistic defaults.
- Reject any candidate for whom the context explicitly contradicts a required constraint.
- Do not change or weaken the meaning of a relationship term merely to produce an answer.
-If no candidate satisfies all required constraints, say that the answer cannot be determined from the provided context.

Examples of semantic constraints:

"sister" requires a sibling relationship and female gender
"brother" requires a sibling relationship and male gender
"daughter" requires a child relationship and female gender
"son" requires a child relationship and male gender

These examples illustrate the principle only. Apply the same semantic reasoning to other relationship terms and constraints without requiring an exhaustive predefined list.

"""

def _extract_entities_with_llm(api_key: str, model: str, user_prompt: str, context:str = "") -> list[str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
                
            },
            {
                "role": "user",
                "content": (
                    f'Context: "{context}"\nQuestion: "{user_prompt}"\n\n'
                    "Example:\n"
                    "Context: \"Hamnet is son of Shakespeare\"\nQuestion: \"Who is the grand child of Shakepeare?\"\n"
                    "Output: {\"answer\": \"\", \"entities_needed\": [\"Hamnet\"]}"
                ),
            },
        ],
        "temperature": 0,
    }

    response = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    raw = response.json()
    choice = raw.get("choices", [{}])[0]
    message = choice.get("message", {}) if isinstance(choice, dict) else {}
    content = str(message.get("content") or "").strip()
    if not content:
        return {"answer": "None", "entities_needed": []}

    extracted: list[str] = []
    try:
        parsed = json.loads(content)
        answer = ""
        extracted = []
        if parsed["action"] == 'fetch_entities':
            extracted = parsed["entities"]
        elif parsed["action"] == "answer":
            answer = parsed["answer"]
        
    except json.JSONDecodeError:
        extracted = []
    rel_prefix_re = re.compile(r'^(?:\.\.?/)+')
    for raw_name in extracted:
        normalized = rel_prefix_re.sub("", raw_name).strip(" .?!")
        if not normalized:
            continue

    deduped: list[str] = []
    for item in extracted:
        if item not in deduped:
            deduped.append(item)


    return {"answer": answer, "entities_needed": deduped}




def _answer_from_combined_context_with_llm(api_key: str, model: str, user_prompt: str, context_text: str) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Answer the user based only on the provided context. "
                    "Be concise, natural, and non-repetitive. "
                    "If context is insufficient, say so briefly. "
                    "Do not invent facts."
                ),
            },
            {
                "role": "user",
                "content": f"User prompt: {user_prompt}\n\nContext:\n{context_text}",
            },
        ],
        "temperature": 0.2,
    }

    response = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    raw = response.json()
    choice = raw.get("choices", [{}])[0]
    message = choice.get("message", {}) if isinstance(choice, dict) else {}
    content = str(message.get("content") or "").strip()
    return content


def _try_multi_entity_context_query(
    mcp: BldrdojoMcpServer,
    api_key: str,
    user_prompt: str,
    model: str,
    session_id: str,
    entities_done: list[dict[str, Any]] = [],
    trace: list[dict[str, Any]] = [],
    level: int = 0
) -> dict[str, Any] | None:
    if level > 5: # too deep recursion, stop
        return {
            "answer": "I could not find enough entity context to answer that reliably.",
            "trace": trace,
            "model": "multi-entity-context-resolver",
            "extracted_entities": None,
            "resolved_entities": None,
            "entity_contexts": None,
        }
    response = _extract_entities_with_llm(api_key=api_key, model=model, user_prompt=user_prompt)
    if level == 0:
        trace.append({"Initial Prompt": user_prompt})
    else:
        trace.append({"New Prompt": user_prompt})
    if response["answer"] == "" and ( not response["entities_needed"] or len(response["entities_needed"]) == 0):
        return {
            "answer": "I could not find enough entity context to answer that reliably.",
            "trace": trace,
            "model": "multi-entity-context-resolver",
            "extracted_entities": None,
            "resolved_entities": None,
            "entity_contexts": None,
        }


        
    entities = response["entities_needed"]
    done_names = [e["requested"] for e in entities_done]
    entities = [e for e in entities if e not in done_names]

    if response["answer"] != "" and len(entities) == 0:
        return {
            "answer": response["answer"],
            "trace": trace,
            "model": "multi-entity-context-resolver",
            "extracted_entities": None,
            "resolved_entities": None,
            "entity_contexts": None,
        }
    
    if len(entities) != 0:
        trace.append(
        {   
            "level": level,
            "entities_needed": entities
        }
    )
    contexts: list[str] = []
    resolved_entities: list[dict[str, Any]] = []
    entity_contexts: list[dict[str, Any]] = []

    for entity_name in entities:
        search_trace = _build_tool_trace(
            mcp=mcp,
            tool_name="search_entities",
            arguments={"query": entity_name, "page_size": 10},
            session_id=session_id,
        )


        search_result = search_trace.get("result", {})
        if not isinstance(search_result, dict) or not search_result.get("ok"):
            continue

        payload = search_result.get("data", {})
        matches = payload.get("matches", []) if isinstance(payload, dict) else []
        if len(matches) > 10:
            return {
            "answer": "Too many records match, make your query more specific",
            "trace": trace,
            "model": "multi-entity-context-resolver",
            "extracted_entities": None,
            "resolved_entities": None,
            "entity_contexts": None,
        }
        for selected in matches:
            entity_id = selected.get("entity_id")

            if not entity_id:
                continue
            ids_done = [e["entity_id"] for e in entities_done]
            if entity_id in ids_done:
                continue

            neighborhood_trace = _build_tool_trace(
                mcp=mcp,
                tool_name="get_entity_neighborhood",
                arguments={"entity_id": entity_id},
                session_id=session_id,
            )


            neighborhood_result = neighborhood_trace.get("result", {})
            if not isinstance(neighborhood_result, dict) or not neighborhood_result.get("ok"):
                continue

            neighborhood_data = neighborhood_result.get("data", {})
            text_block = ""
            if isinstance(neighborhood_data, dict):
                text_block = str(neighborhood_data.get("text", "")).strip()
            if not text_block:
                continue

            display_name = str(selected.get("name") or entity_name).strip() or entity_name
            trace.append({"context":{"entity":display_name, "text":text_block}})
            contexts.append(f"{text_block}\n")
            entities_done.append({"requested": entity_name, "entity_id": entity_id, "name": display_name})
            resolved_entities.append({"requested": entity_name, "entity_id": entity_id, "name": display_name})
            entity_contexts.append(
              {
                 "requested_entity": entity_name,
                "resolved_entity": {
                    "entity_id": entity_id,
                    "name": display_name,
                },
                "search_backend_queries": search_trace.get("actual_rest_calls"),
                "neighborhood_backend_query": neighborhood_trace.get("actual_rest_call"),
                "received_text": text_block,
              }
            )


    combined_context = "\n\n".join(contexts)
    
    user_prompt = f"Context:{combined_context}\n{user_prompt}"
    return _try_multi_entity_context_query(mcp, api_key, user_prompt, model, session_id, entities_done, trace, level+1)

  

def _run_llm_with_mcp(
    mcp: BldrdojoMcpServer,
    api_key: str,
    user_prompt: str,
    model: str,
    session_id: str,
    max_tool_rounds: int = 5,
) -> dict[str, Any]:
    mcp_tools = mcp.list_tools()
    two_step_tools = {"search_entities", "get_entity_neighborhood"}
    mcp_tools = [tool for tool in mcp_tools if tool.get("name") in two_step_tools]
    llm_tools, safe_to_original = _to_openai_tools(mcp_tools)

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant. You may call tools when needed. "
                "Use a strict two-step retrieval workflow. "
                "Step 1: call search_entities(query=...) to resolve the subject to entity_id. "
                "For search_entities, pass only the entity name fragment (for example 'Rahul Kalra'), not the whole user sentence. "
                "Step 2: call get_entity_neighborhood(entity_id=...) and answer only from that returned context. "
                "In get_entity_neighborhood results, treat data.text as the primary source of truth and prioritize key facts from it. "
                "If multiple candidates are returned, pick the best exact name match; if still ambiguous, ask a short clarification. "
                "You might need to make multiple calls to get_entity_neighbourhood if relation of relation kind of query is needed."
                "For example, to find grandparent you will need to make a neighbourhood query for the parent entity first, "
                "and then another neighbourhood query for the grandparent entity. "
                "If multiple candidates are returned, pick the best exact name match; if still ambiguous, ask a short clarification. "
                "Format as a nice paragraph starting with the phrase: This is what I know. Exclude photos and locations in the output."
                "Do not invent facts not present in tool results."
            ),
        },
        {"role": "user", "content": user_prompt},
    ]

    trace: list[dict[str, Any]] = []

    for _ in range(max_tool_rounds):
        raw = _openai_chat(api_key=api_key, model=model, messages=messages, tools=llm_tools)
        choice = raw.get("choices", [{}])[0]
        message = choice.get("message", {})
        tool_calls = message.get("tool_calls") or []

        assistant_content = message.get("content") or ""

        # Add assistant response (with tool call envelope if present)
        if tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_content,
                    "tool_calls": tool_calls,
                }
            )
        else:
            messages.append({"role": "assistant", "content": assistant_content})

        if not tool_calls:
            return {
                "answer": assistant_content,
                "trace": trace,
                "model": model,
            }

        for call in tool_calls:
            call_id = call.get("id", "")
            fn = call.get("function", {})
            safe_name = fn.get("name", "")
            name = safe_to_original.get(safe_name, safe_name)
            raw_args = fn.get("arguments", "{}")
            try:
                parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except json.JSONDecodeError:
                parsed_args = {}

            call_plan = mcp.describe_tool_call(name=name, arguments=parsed_args)
            tool_result = mcp.call_tool(name=name, arguments=parsed_args, session_id=session_id)
            backend_data = tool_result.get("data") if isinstance(tool_result, dict) else None
            backend_error = tool_result.get("error") if isinstance(tool_result, dict) else None
            tool_meta = tool_result.get("meta") if isinstance(tool_result, dict) else None
            actual_rest_call = tool_meta.get("backend_call") if isinstance(tool_meta, dict) else None
            actual_rest_calls = tool_meta.get("internal_calls") if isinstance(tool_meta, dict) else None
            trace.append(
                {
                    "tool": name,
                    "llm_tool_name": safe_name,
                    "mcp_call": {
                        "name": name,
                        "arguments": parsed_args,
                        "session_id": session_id,
                    },
                    "rest_call": call_plan,
                    "actual_rest_call": actual_rest_call,
                    "actual_rest_calls": actual_rest_calls,
                    "backend_data": backend_data,
                    "backend_error": backend_error,
                    "arguments": parsed_args,
                    "result": tool_result,
                }
            )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(tool_result, ensure_ascii=True),
                }
            )

    return {
        "answer": "Reached max tool-call rounds before final answer.",
        "trace": trace,
        "model": model,
    }


def _build_tool_trace(
    mcp: BldrdojoMcpServer,
    tool_name: str,
    arguments: dict[str, Any],
    session_id: str,
) -> dict[str, Any]:
    rest_call = mcp.describe_tool_call(name=tool_name, arguments=arguments)
    result = mcp.call_tool(name=tool_name, arguments=arguments, session_id=session_id)
    backend_data = result.get("data") if isinstance(result, dict) else None
    backend_error = result.get("error") if isinstance(result, dict) else None
    result_meta = result.get("meta") if isinstance(result, dict) else None
    actual_rest_call = result_meta.get("backend_call") if isinstance(result_meta, dict) else None
    actual_rest_calls = result_meta.get("internal_calls") if isinstance(result_meta, dict) else None
    return {
        "tool": tool_name,
        "mcp_call": {
            "name": tool_name,
            "arguments": arguments,
            "session_id": session_id,
        },
        "rest_call": rest_call,
        "actual_rest_call": actual_rest_call,
        "actual_rest_calls": actual_rest_calls,
        "backend_data": backend_data,
        "backend_error": backend_error,
        "result": result,
    }


RELATION_INTENTS: dict[str, dict[str, str]] = {
    "parents": {
        "relation_type": "IS_CHILD_OF",
        "list_prefix": "Parents of {name}",
        "none": "No parent relations were found for {name}.",
        "count_zero": "{name} has 0 parents in the current relation data.",
        "count_one": "{name} has 1 parent: {items}.",
        "count_many": "{name} has {count} parents: {items}.",
    },
    "children": {
        "relation_type": "IS_PARENT_OF",
        "list_prefix": "Children of {name}",
        "none": "No child relations were found for {name}.",
        "count_zero": "{name} has 0 children in the current relation data.",
        "count_one": "{name} has 1 child: {items}.",
        "count_many": "{name} has {count} children: {items}.",
    },
    "workplaces": {
        "relation_type": "WORKS_AT",
        "list_prefix": "Workplaces of {name}",
        "none": "No workplace relations were found for {name}.",
        "count_zero": "{name} has 0 workplaces in the current relation data.",
        "count_one": "{name} works at {items}.",
        "count_many": "{name} works at {items}.",
    },
    "residences": {
        "relation_type": "LIVES_AT",
        "list_prefix": "Residence of {name}",
        "none": "No residence relations were found for {name}.",
        "count_zero": "{name} has 0 residences in the current relation data.",
        "count_one": "{name} lives at {items}.",
        "count_many": "{name} lives at {items}.",
    },
}

RELATION_QUERY_PATTERNS: list[tuple[str, str, str]] = [
    (r"^\s*find\s+parent(?:s)?\s+of\s+(.+?)\s*[?.!]*\s*$", "parents", "list"),
    (r"^\s*who\s+is\s+the\s+parent(?:s)?\s+of\s+(.+?)\s*[?.!]*\s*$", "parents", "list"),
    (r"^\s*who\s+are\s+the\s+parent(?:s)?\s+of\s+(.+?)\s*[?.!]*\s*$", "parents", "list"),
    (r"^\s*parent(?:s)?\s+of\s+(.+?)\s*[?.!]*\s*$", "parents", "list"),
    (r"^\s*how\s+many\s+parent(?:s)?\s+does\s+(.+?)\s+have\s*[?.!]*\s*$", "parents", "count"),
    (r"^\s*who\s+is\s+the\s+child\s+of\s+(.+?)\s*[?.!]*\s*$", "children", "list"),
    (r"^\s*who\s+is\s+child\s+of\s+(.+?)\s*[?.!]*\s*$", "children", "list"),
    (r"^\s*who\s+are\s+the\s+children\s+of\s+(.+?)\s*[?.!]*\s*$", "children", "list"),
    (r"^\s*who\s+are\s+children\s+of\s+(.+?)\s*[?.!]*\s*$", "children", "list"),
    (r"^\s*children\s+of\s+(.+?)\s*[?.!]*\s*$", "children", "list"),
    (r"^\s*child\s+of\s+(.+?)\s*[?.!]*\s*$", "children", "list"),
    (r"^\s*how\s+many\s+children\s+does\s+(.+?)\s+have\s*[?.!]*\s*$", "children", "count"),
    (r"^\s*how\s+many\s+children\s+(.+?)\s+has\s*[?.!]*\s*$", "children", "count"),
    (r"^\s*number\s+of\s+children\s+of\s+(.+?)\s*[?.!]*\s*$", "children", "count"),
    (r"^\s*where\s+does\s+(.+?)\s+work(?:\s+at)?\s*[?.!]*\s*$", "workplaces", "list"),
    (r"^\s*where\s+do\s+(.+?)\s+work(?:\s+at)?\s*[?.!]*\s*$", "workplaces", "list"),
    (r"^\s*which\s+company\s+does\s+(.+?)\s+work(?:\s+at)?\s*[?.!]*\s*$", "workplaces", "list"),
    (r"^\s*where\s+does\s+(.+?)\s+live\s*[?.!]*\s*$", "residences", "list"),
    (r"^\s*where\s+do(?:es)?\s+(.+?)\s+live\s*[?.!]*\s*$", "residences", "list"),
]


def _extract_relation_query(prompt: str) -> tuple[str, str, str] | None:
    for pattern, intent, mode in RELATION_QUERY_PATTERNS:
        m = re.match(pattern, prompt, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip(), intent, mode
    return None


def _select_exact_or_first(results: list[dict[str, Any]], target_name: str) -> dict[str, Any] | None:
    lowered_target = target_name.casefold()
    for row in results:
        if str(row.get("display", "")).casefold() == lowered_target:
            return row
    return results[0] if results else None


def _extract_entity_info_target(prompt: str) -> str | None:
    patterns = [
        r"^\s*tell\s+me\s+about\s+(.+?)\s*[?.!]*\s*$",
        r"^\s*what\s+do\s+you\s+know\s+about\s+(.+?)\s*[?.!]*\s*$",
        r"^\s*details\s+about\s+(.+?)\s*[?.!]*\s*$",
        r"^\s*info(?:rmation)?\s+about\s+(.+?)\s*[?.!]*\s*$",
        r"^\s*who\s+is\s+(.+?)\s*[?.!]*\s*$",
    ]
    for pattern in patterns:
        m = re.match(pattern, prompt, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _select_entity_match(matches: list[dict[str, Any]], target_name: str) -> dict[str, Any] | None:
    lowered_target = target_name.casefold()
    for row in matches:
        name = str(row.get("name", "")).casefold()
        if name == lowered_target:
            return row
    for row in matches:
        name = str(row.get("name", "")).casefold()
        if lowered_target in name or name in lowered_target:
            return row
    return matches[0] if matches else None


def _try_direct_entity_info_query(
    mcp: BldrdojoMcpServer,
    user_prompt: str,
    session_id: str,
) -> dict[str, Any] | None:
    target_name = _extract_entity_info_target(user_prompt)
    if not target_name:
        return None

    trace: list[dict[str, Any]] = []

    search_trace = _build_tool_trace(
        mcp=mcp,
        tool_name="search_entities",
        arguments={"query": target_name, "page_size": 10},
        session_id=session_id,
    )
    trace.append(search_trace)

    search_result = search_trace.get("result", {})
    if not isinstance(search_result, dict) or not search_result.get("ok"):
        return {
            "answer": f"I could not look up {target_name} due to an entity lookup error.",
            "trace": trace,
            "model": "deterministic-entity-info-resolver",
        }

    payload = search_result.get("data", {})
    matches = payload.get("matches", []) if isinstance(payload, dict) else []
    selected = _select_entity_match(matches if isinstance(matches, list) else [], target_name)
    if selected is None:
        return {
            "answer": f"I could not find any information about {target_name}.",
            "trace": trace,
            "model": "deterministic-entity-info-resolver",
        }

    entity_id = selected.get("entity_id")
    if not entity_id:
        return {
            "answer": f"I found {target_name} but could not resolve entity id.",
            "trace": trace,
            "model": "deterministic-entity-info-resolver",
        }

    neighborhood_trace = _build_tool_trace(
        mcp=mcp,
        tool_name="get_entity_neighborhood",
        arguments={"entity_id": entity_id},
        session_id=session_id,
    )
    trace.append(neighborhood_trace)

    neighborhood_result = neighborhood_trace.get("result", {})
    if not isinstance(neighborhood_result, dict) or not neighborhood_result.get("ok"):
        return {
            "answer": f"I found {selected.get('name', target_name)} but could not load full context.",
            "trace": trace,
            "model": "deterministic-entity-info-resolver",
        }

    neighborhood_data = neighborhood_result.get("data", {})
    text_block = ""
    if isinstance(neighborhood_data, dict):
        text_block = str(neighborhood_data.get("text", "")).strip()

    answer = text_block or f"I found {selected.get('name', target_name)} but no detailed context text was returned."
    return {
        "answer": answer,
        "trace": trace,
        "model": "deterministic-entity-info-resolver",
    }


def _format_relation_answer(intent: str, mode: str, display_name: str, items: list[str]) -> str:
    spec = RELATION_INTENTS[intent]
    count = len(items)
    joined = ", ".join(items)

    if mode == "count":
        if count == 0:
            return spec["count_zero"].format(name=display_name, count=count, items=joined)
        if count == 1:
            return spec["count_one"].format(name=display_name, count=count, items=joined)
        return spec["count_many"].format(name=display_name, count=count, items=joined)

    if count == 0:
        return spec["none"].format(name=display_name)
    return f"{spec['list_prefix'].format(name=display_name)}: {joined}"


def _try_direct_relation_query(
    mcp: BldrdojoMcpServer,
    user_prompt: str,
    session_id: str,
) -> dict[str, Any] | None:
    parsed = _extract_relation_query(user_prompt)
    if not parsed:
        return None

    target_name, intent, mode = parsed
    trace: list[dict[str, Any]] = []

    list_args = {"search": target_name, "type": "Person", "page_size": 10}
    list_trace = _build_tool_trace(mcp, "entities.list", list_args, session_id)
    trace.append(list_trace)

    list_result = list_trace["result"]
    if not list_result.get("ok"):
        return {
            "answer": f"I could not look up {target_name} due to an entity lookup error.",
            "trace": trace,
            "model": "deterministic-relation-resolver",
        }

    payload = list_result.get("data", {})
    results = payload.get("results", []) if isinstance(payload, dict) else []
    if not results:
        return {
            "answer": f"I could not find a person named {target_name}.",
            "trace": trace,
            "model": "deterministic-relation-resolver",
        }

    selected = _select_exact_or_first(results, target_name)
    if selected is None:
        return {
            "answer": f"I could not find a person named {target_name}.",
            "trace": trace,
            "model": "deterministic-relation-resolver",
        }

    entity_id = selected.get("id")
    if not entity_id:
        return {
            "answer": f"I found {target_name} but the entity id was missing.",
            "trace": trace,
            "model": "deterministic-relation-resolver",
        }

    rel_trace = _build_tool_trace(mcp, "entities.relations", {"id": entity_id}, session_id)
    trace.append(rel_trace)

    rel_result = rel_trace["result"]
    if not rel_result.get("ok"):
        return {
            "answer": f"I found {selected.get('display', target_name)} but could not fetch relations.",
            "trace": trace,
            "model": "deterministic-relation-resolver",
        }

    rel_payload = rel_result.get("data", {})
    outgoing = rel_payload.get("outgoing", []) if isinstance(rel_payload, dict) else []
    wanted_relation_type = RELATION_INTENTS[intent]["relation_type"]

    matches: list[str] = []
    for rel in outgoing:
        if str(rel.get("relation_type", "")).upper() != wanted_relation_type:
            continue
        entity = rel.get("entity", {})
        name = entity.get("display")
        if isinstance(name, str) and name and name not in matches:
            matches.append(name)

    display_name = selected.get("display", target_name)
    answer = _format_relation_answer(intent=intent, mode=mode, display_name=display_name, items=matches)

    return {
        "answer": answer,
        "trace": trace,
        "model": "deterministic-relation-resolver",
    }


class PromptFrontendHandler(BaseHTTPRequestHandler):
    mcp_server = BldrdojoMcpServer()
    html = _load_html()

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send_bytes(200, self.html, "text/html; charset=utf-8")
            return
        if self.path == "/api/version":
            self._send_json(200, {"ok": True, "data": {"version": FRONTEND_VERSION}})
            return
        if self.path == "/api/google/config":
            try:
                resp = _backend_get("/api/auth/google/url/")
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
                return
            except requests.RequestException as exc:
                self._send_json(502, {"ok": False, "error": {"message": f"Backend network error: {exc}"}})
                return

        if self.path.startswith("/api/auth/status"):
            session_id = "web-default"
            if "?" in self.path:
                qs = self.path.split("?", 1)[1]
                for part in qs.split("&"):
                    if part.startswith("session_id="):
                        session_id = part.split("=", 1)[1] or "web-default"
                        break

            authenticated = self.mcp_server.has_session_auth(session_id)
            user_info: dict[str, Any] | None = None
            entities_count: int | None = None

            if authenticated:
                who = self.mcp_server.call_tool("auth.current_user", session_id=session_id)
                if who.get("ok"):
                    data = who.get("data")
                    if isinstance(data, dict):
                        user_info = data

                count_resp = self.mcp_server.call_tool(
                    "entities.list",
                    arguments={"page_size": 1},
                    session_id=session_id,
                )
                if count_resp.get("ok"):
                    data = count_resp.get("data")
                    if isinstance(data, dict) and isinstance(data.get("count"), int):
                        entities_count = data.get("count")

            self._send_json(
                200,
                {
                    "ok": True,
                    "data": {
                        "authenticated": authenticated,
                        "user": user_info or {},
                        "entities_count": entities_count,
                    },
                },
            )
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
                resp = _backend_post("/api/auth/google/", {"access_token": access_token}, timeout=60)
                data = resp.json() if "application/json" in resp.headers.get("Content-Type", "") else {"raw": resp.text}
                if not resp.ok:
                    self._send_json(502, {"ok": False, "error": {"message": "Google exchange failed", "details": data}})
                    return

                jwt_access = data.get("access")
                jwt_refresh = data.get("refresh")
                if not jwt_access:
                    self._send_json(502, {"ok": False, "error": {"message": "Google exchange did not return JWT access token", "details": data}})
                    return

                self.mcp_server.set_session_auth(session_id=session_id, access=jwt_access, refresh=jwt_refresh)
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
                return
            except requests.RequestException as exc:
                self._send_json(502, {"ok": False, "error": {"message": f"Backend network error: {exc}"}})
                return

        if self.path != "/api/chat":
            self._send_json(404, {"ok": False, "error": {"message": "Not found"}})
            return

        try:
            payload = self._read_json_body()
        except ValueError as exc:
            self._send_json(400, {"ok": False, "error": {"message": str(exc)}})
            return

        request_api_key = str(payload.get("api_key", "")).strip()
        api_key = _resolve_openai_api_key(request_api_key)
        prompt = str(payload.get("prompt", "")).strip()
        model = str(payload.get("model", DEFAULT_MODEL)).strip() or DEFAULT_MODEL
        session_id = str(payload.get("session_id", "web-default")).strip() or "web-default"

        if not api_key:
            self._send_json(
                400,
                {
                    "ok": False,
                    "error": {
                        "message": "No OpenAI API key available. Provide api_key in UI/request or set OPENAI_API_KEY in environment/.env",
                    },
                },
            )
            return
        if not prompt:
            self._send_json(400, {"ok": False, "error": {"message": "prompt is required"}})
            return

        try:
            multi_entity_info = _try_multi_entity_context_query(
                mcp=self.mcp_server,
                api_key=api_key,
                user_prompt=prompt,
                model=model,
                session_id=session_id,
                trace=[],
                entities_done=[], level=0
            )
            if multi_entity_info is not None:
                self._send_json(200, {"ok": True, "data": multi_entity_info})
                return

            direct_relation_info = _try_direct_relation_query(
                mcp=self.mcp_server,
                user_prompt=prompt,
                session_id=session_id,
            )
            if direct_relation_info is not None:
                raw_answer = str(direct_relation_info.get("answer", "")).strip()
                if raw_answer:
                    try:
                        cleaned_answer = _cleanup_answer_with_llm(
                            api_key=api_key,
                            model=model,
                            user_prompt=prompt,
                            raw_text=raw_answer,
                        )
                        direct_relation_info["answer"] = cleaned_answer
                        direct_relation_info["cleanup"] = {"applied": True, "mode": "llm_rewrite"}
                    except (requests.RequestException, ValueError, KeyError):
                        direct_relation_info["cleanup"] = {"applied": False, "mode": "llm_rewrite", "fallback": "raw"}
                self._send_json(200, {"ok": True, "data": direct_relation_info})
                return

            direct_entity_info = _try_direct_entity_info_query(
                mcp=self.mcp_server,
                user_prompt=prompt,
                session_id=session_id,
            )
            if direct_entity_info is not None:
                raw_answer = str(direct_entity_info.get("answer", "")).strip()
                if raw_answer:
                    try:
                        cleaned_answer = _cleanup_answer_with_llm(
                            api_key=api_key,
                            model=model,
                            user_prompt=prompt,
                            raw_text=raw_answer,
                        )
                        direct_entity_info["answer"] = cleaned_answer
                        direct_entity_info["cleanup"] = {"applied": True, "mode": "llm_rewrite"}
                    except (requests.RequestException, ValueError, KeyError):
                        direct_entity_info["cleanup"] = {"applied": False, "mode": "llm_rewrite", "fallback": "raw"}
                self._send_json(200, {"ok": True, "data": direct_entity_info})
                return

            result = _run_llm_with_mcp(
                mcp=self.mcp_server,
                api_key=api_key,
                user_prompt=prompt,
                model=model,
                session_id=session_id,
            )
        except requests.HTTPError as exc:
            body_text = exc.response.text if exc.response is not None else str(exc)
            self._send_json(502, {"ok": False, "error": {"message": "LLM request failed", "details": body_text}})
            return
        except requests.RequestException as exc:
            self._send_json(502, {"ok": False, "error": {"message": f"Network error: {exc}"}})
            return
        except Exception as exc:  # pragma: no cover
            self._send_json(500, {"ok": False, "error": {"message": str(exc)}})
            return

        self._send_json(200, {"ok": True, "data": result})

    def _read_json_body(self) -> dict[str, Any]:
        length_header = self.headers.get("Content-Length")
        if not length_header:
            raise ValueError("Missing Content-Length")
        length = int(length_header)
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc

    def _send_json(self, status_code: int, obj: dict[str, Any]) -> None:
        data = json.dumps(obj, ensure_ascii=True).encode("utf-8")
        self._send_bytes(status_code, data, "application/json; charset=utf-8")

    def _send_bytes(self, status_code: int, data: bytes, content_type: str) -> None:
        self.send_response(status_code)
        self._set_common_headers(content_type, len(data))
        self.end_headers()
        self.wfile.write(data)

    def _set_common_headers(self, content_type: str, content_length: int) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(content_length))
        # Allow testing UI from other local origins (for example static file server).
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def log_message(self, format_str: str, *args: Any) -> None:
        # Keep output concise for local dev
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), PromptFrontendHandler)
    print(f"Prompt frontend {FRONTEND_VERSION} listening on http://{HOST}:{PORT}")
    print("Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
