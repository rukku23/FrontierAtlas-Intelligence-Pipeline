"""Gemini LLM Provider implementation using google-genai or direct REST API."""
import os
import asyncio
from typing import Type, Optional, TypeVar
from pydantic import BaseModel
from src.extraction.llm_provider import LLMProvider
from src.utils.logger import logger

T = TypeVar("T", bound=BaseModel)

class GeminiProvider(LLMProvider):
    """Gemini 1.5 Flash Provider."""

    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-1.5-flash"):
        key = api_key or os.getenv("GEMINI_API_KEY")
        super().__init__(name="GeminiProvider", model_name=model_name, api_key=key)

    async def extract(self, text: str, schema_class: Type[T]) -> Optional[T]:
        if not self.api_key:
            logger.warning("Gemini API key missing, skipping provider", extra={"component": self.name})
            return None

        system_prompt = self.build_system_prompt(schema_class)
        untrusted_text = self.sanitize_untrusted_input(text)
        full_prompt = f"{system_prompt}\n\nEXTRACT FROM THIS TEXT:\n{untrusted_text}"

        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            # Run blocking API call in executor thread to prevent loop blocking
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=self.model_name,
                contents=full_prompt
            )
            raw_response = response.text if hasattr(response, "text") else str(response)
            data = self.extract_json_from_response(raw_response)
            if data:
                return schema_class.model_validate(data)
        except Exception as e:
            logger.warning(f"Gemini extraction error: {e}", extra={"component": self.name, "error": str(e)})
            raise e  # Re-raise for fallback orchestrator handling (429/errors)

        return None
