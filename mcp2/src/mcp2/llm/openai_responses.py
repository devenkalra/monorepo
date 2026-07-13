from __future__ import annotations

import json
from typing import Any

import requests

from .planner import Planner, PlannerAction, PlannerContext


class OpenAIResponsesPlanner(Planner):
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4.1-mini",
        responses_url: str = "https://api.openai.com/v1/responses",
        timeout_seconds: int = 60,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.responses_url = responses_url
        self.timeout_seconds = timeout_seconds

    async def next_action(self, context: PlannerContext, previous_response_id: str | None) -> tuple[PlannerAction, str | None]:
        system_prompt = """
You answer questions by reasoning over an iteratively retrieved knowledge graph.

Use tools logically: fetch known entities, traverse stored relationships, or answer.

Convert every requested semantic relationship into a complete traversal plan using only relationships listed in the KG schema. Derived relationships may require multiple hops. Continue traversing until each requested relationship is resolved or no useful path remains.

Treat each requested relationship or constraint independently. Do not stop after resolving only part of a multi-part question.

Before answering, identify candidate entities and verify the requested relationship and all implied constraints.

A discovered entity may be only partially known. If a relevant candidate has unresolved attributes or relationships needed to accept or reject it, fetch that entity before answering.

Do not treat missing information as evidence that a constraint is false.

Before answering unknown or giving a partial answer, check whether additional entity fetching or relationship traversal could materially change any unresolved part of the answer.

Final answers must be entity-grounded. For every entity mentioned in the answer, copy its display name exactly from the Entities mapping. Never generate a new entity name or variation that is absent from that mapping.

Return only JSON in one of forms:

{"action":"fetch_entities","entities":["p1"]}

{"action":"traverse_relation","entity":"p1","relationship":"child_of","direction":"in"}

{"action":"answer","answer":"..."}


        """

        user_blob = {
            "question": context.question,
            "kg_schema": context.schema_text,
            "known_entities": context.known_entities,
            "known_facts": context.known_facts,
            "new_entities": context.new_entities,
            "new_facts": context.new_facts,
        }

        payload: dict[str, Any] = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_blob, ensure_ascii=True)},
            ],
            "temperature": 0,
        }
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        response = requests.post(
            self.responses_url,
            headers=headers,
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()

        response_id = data.get("id")
        text = self._extract_output_text(data)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Planner returned non-JSON output: {text}") from exc

        parsed = self._normalize_answer_payload(parsed)

        action = PlannerAction.model_validate(parsed)
        return action, response_id

    @staticmethod
    def _extract_output_text(response_json: dict[str, Any]) -> str:
        output = response_json.get("output", [])
        for item in output:
            content = item.get("content", [])
            for part in content:
                if part.get("type") in {"output_text", "text"} and isinstance(part.get("text"), str):
                    return part["text"].strip()
        # fallback fields
        text = response_json.get("output_text")
        if isinstance(text, str):
            return text.strip()
        raise ValueError("No text output found in OpenAI response")

    @staticmethod
    def _normalize_answer_payload(payload: Any) -> Any:
        if not isinstance(payload, dict):
            return payload

        if payload.get("action") != "answer":
            return payload

        answer = payload.get("answer")
        if isinstance(answer, str) or answer is None:
            return payload

        payload = dict(payload)
        payload["answer"] = OpenAIResponsesPlanner._stringify_answer(answer)
        return payload

    @staticmethod
    def _stringify_answer(answer: Any) -> str:
        if isinstance(answer, str):
            return answer
        if isinstance(answer, dict):
            if not answer:
                return ""
            keys = [str(key) for key in answer.keys() if str(key).strip()]
            if len(keys) == 1:
                return keys[0]
            return ", ".join(keys)
        if isinstance(answer, list):
            items = [OpenAIResponsesPlanner._stringify_answer(item) for item in answer]
            items = [item for item in items if item]
            return ", ".join(items)
        return str(answer)
