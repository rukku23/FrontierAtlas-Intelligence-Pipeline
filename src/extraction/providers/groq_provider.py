"""Groq LLM Provider implementation using groq SDK."""
import os
import asyncio
from typing import Type, Optional, TypeVar
from pydantic import BaseModel
from src.extraction.llm_provider import LLMProvider, is_valid_api_key
from src.utils.logger import logger

T = TypeVar("T", bound=BaseModel)

class GroqProvider(LLMProvider):
    """Groq Llama 3 Provider."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        key = api_key or os.getenv("GROQ_API_KEY")
        model = model_name or os.getenv("GROQ_MODEL") or "llama-3.1-70b-versatile"
        super().__init__(name="GroqProvider", model_name=model, api_key=key)

    async def extract(self, text: str, schema_class: Type[T]) -> Optional[T]:
        if not self.api_key:
            logger.warning("Groq API key missing or invalid, skipping provider", extra={"component": self.name})
            return None

        system_prompt = self.build_system_prompt(schema_class)
        untrusted_text = self.sanitize_untrusted_input(text)

        try:
            from groq import Groq
            client = Groq(api_key=self.api_key)
            completion = await asyncio.to_thread(
                client.chat.completions.create,
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": untrusted_text}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            raw_response = completion.choices[0].message.content
            data = self.extract_json_from_response(raw_response)
            if data:
                return schema_class.model_validate(data)
        except Exception as e:
            logger.warning(f"Groq extraction error: {e}", extra={"component": self.name, "error": str(e)})
            raise e

        return None
