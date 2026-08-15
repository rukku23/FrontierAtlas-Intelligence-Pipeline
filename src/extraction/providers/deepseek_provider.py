"""DeepSeek LLM Provider implementation using OpenAI compatible client."""
import os
import asyncio
from typing import Type, Optional, TypeVar
from pydantic import BaseModel
from src.extraction.llm_provider import LLMProvider
from src.utils.logger import logger

T = TypeVar("T", bound=BaseModel)

class DeepSeekProvider(LLMProvider):
    """DeepSeek Provider."""

    def __init__(self, api_key: Optional[str] = None, model_name: str = "deepseek-chat"):
        key = api_key or os.getenv("DEEPSEEK_API_KEY")
        super().__init__(name="DeepSeekProvider", model_name=model_name, api_key=key)

    async def extract(self, text: str, schema_class: Type[T]) -> Optional[T]:
        if not self.api_key:
            logger.warning("DeepSeek API key missing, skipping provider", extra={"component": self.name})
            return None

        system_prompt = self.build_system_prompt(schema_class)
        untrusted_text = self.sanitize_untrusted_input(text)

        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com")
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
            logger.warning(f"DeepSeek extraction error: {e}", extra={"component": self.name, "error": str(e)})
            raise e

        return None
