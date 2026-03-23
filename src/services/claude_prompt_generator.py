import json
from typing import List, Optional

from anthropic import Anthropic

from src.config.settings import settings

SYSTEM_PROMPT = (
    "You generate natural-language search prompts that a user would type "
    "when looking for documents, forms, or templates. "
    "Each prompt should read like a real user query — conversational, "
    "specific, and action-oriented. "
    "Use one placeholder like ___ where the user should fill in their own detail. "
    'Return ONLY valid JSON: {"prompt":["..."]}'
)


class ClaudePromptGenerator:
    def __init__(self):
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is not configured")
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model

    def generate(
        self,
        query: Optional[str] = None,
        context: Optional[str] = None,
        count: int = 3,
    ) -> List[str]:
        parts: list[str] = []
        if context:
            parts.append(f"Context / rules:\n{context}")
        if query:
            parts.append(f"User request:\n{query}")

        user_text = (
            f"Generate {count} distinct search prompt templates.\n\n"
            + "\n\n".join(parts)
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_text}],
        )

        text_blocks = [b.text for b in response.content if getattr(b, "type", "") == "text"]
        raw_text = "\n".join(text_blocks).strip()

        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("Claude response is not valid JSON")

        data = json.loads(raw_text[start : end + 1])
        prompts = data.get("prompt", data.get("prompts", []))
        if not isinstance(prompts, list) or not all(isinstance(p, str) for p in prompts):
            raise ValueError("Claude JSON does not contain a valid prompt list")

        return prompts[:count]
