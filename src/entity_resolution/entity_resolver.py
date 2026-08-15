"""Deterministic Entity Resolution Engine using RapidFuzz with 50 seed AI entities and audit logging."""
import re
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timezone
from rapidfuzz import fuzz, process
from src.utils.logger import logger
from src.utils.config import get_config

# Seed Canonical AI Companies
CANONICAL_AI_ENTITIES = [
    "OpenAI", "Anthropic", "Google DeepMind", "Meta AI", "Microsoft AI",
    "Mistral AI", "Cohere", "Scale AI", "Hugging Face", "Perplexity AI",
    "Stability AI", "Midjourney", "Runway", "ElevenLabs", "Pinecone",
    "Weaviate", "Qdrant", "Chroma", "LangChain", "LlamaIndex",
    "Anyscale", "Together AI", "Groq", "Cerebras", "SambaNova",
    "Modal", "Baseten", "Replicate", "Fireworks AI", "Databricks",
    "Snowflake", "Weights & Biases", "Neptune.ai", "Comet", "Vellum",
    "Portkey", "Humanloop", "Honeyhive", "Braintrust", "PromptLayer",
    "Helicone", "Arize AI", "Arthur AI", "Cleanlab", "Supervisely",
    "Roboflow", "Labelbox", "V7 Labs", "Appen", "DeepL"
]

# Explicit Aliases Mapping
KNOWN_ALIASES: Dict[str, str] = {
    "openai": "OpenAI",
    "open ai": "OpenAI",
    "openai inc": "OpenAI",
    "openai, inc.": "OpenAI",
    "anthropic": "Anthropic",
    "anthropic pbc": "Anthropic",
    "deepmind": "Google DeepMind",
    "google deepmind": "Google DeepMind",
    "deepmind technologies": "Google DeepMind",
    "meta ai": "Meta AI",
    "meta ai research": "Meta AI",
    "fair": "Meta AI",
    "microsoft ai": "Microsoft AI",
    "mistral": "Mistral AI",
    "mistral ai": "Mistral AI",
    "huggingface": "Hugging Face",
    "hugging face": "Hugging Face",
    "perplexity": "Perplexity AI",
    "perplexity ai": "Perplexity AI",
    "stability": "Stability AI",
    "stability ai": "Stability AI",
    "stability.ai": "Stability AI",
    "runwayml": "Runway",
    "runway research": "Runway",
    "eleven labs": "ElevenLabs",
    "wandb": "Weights & Biases",
    "weights and biases": "Weights & Biases",
}

class EntityResolutionResult:
    def __init__(
        self,
        raw_name: str,
        canonical_name: str,
        match_method: str,
        confidence: float,
        source_url: str,
        timestamp: str
    ):
        self.raw_name = raw_name
        self.canonical_name = canonical_name
        self.match_method = match_method
        self.confidence = confidence
        self.source_url = source_url
        self.timestamp = timestamp

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_name": self.raw_name,
            "canonical_name": self.canonical_name,
            "match_method": self.match_method,
            "confidence": round(self.confidence, 2),
            "source_url": self.source_url,
            "timestamp": self.timestamp
        }

class EntityResolver:
    """Deterministic Entity Resolver using exact, alias, and RapidFuzz matching."""

    def __init__(
        self,
        canonical_entities: Optional[List[str]] = None,
        aliases: Optional[Dict[str, str]] = None,
        fuzzy_threshold: float = 85.0
    ):
        self.canonical_entities = canonical_entities or CANONICAL_AI_ENTITIES
        self.aliases = aliases or KNOWN_ALIASES
        self.fuzzy_threshold = fuzzy_threshold
        self.resolution_logs: List[EntityResolutionResult] = []

        # Normalized mapping for exact lookup
        self.normalized_canonical_map: Dict[str, str] = {
            self.normalize_string(name): name for name in self.canonical_entities
        }

    @staticmethod
    def normalize_string(text: str) -> str:
        """Normalize string: lowercase, strip legal suffixes, collapse whitespace."""
        if not text:
            return ""
        clean = text.lower().strip()
        # Remove common corporate suffixes
        clean = re.sub(r"\b(inc|corp|corporation|ltd|limited|pbc|llc|gmbh|co|company)\b", "", clean)
        clean = re.sub(r"[^\w\s]", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    def resolve(self, raw_name: str, source_url: str = "") -> EntityResolutionResult:
        """
        Resolve raw company name to canonical entity using pipeline:
        Normalization -> Exact -> Alias -> RapidFuzz -> Threshold Gate -> Canonical/Unresolved
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        if not raw_name or not raw_name.strip():
            res = EntityResolutionResult(raw_name, "Unresolved", "NONE", 0.0, source_url, now_iso)
            self.resolution_logs.append(res)
            return res

        norm_name = self.normalize_string(raw_name)

        # 1. Exact Match against Normalized Seed List
        if norm_name in self.normalized_canonical_map:
            canonical = self.normalized_canonical_map[norm_name]
            res = EntityResolutionResult(raw_name, canonical, "EXACT", 100.0, source_url, now_iso)
            self.resolution_logs.append(res)
            return res

        # 2. Alias Table Match
        if norm_name in self.aliases:
            canonical = self.aliases[norm_name]
            res = EntityResolutionResult(raw_name, canonical, "ALIAS", 100.0, source_url, now_iso)
            self.resolution_logs.append(res)
            return res

        # 3. RapidFuzz Match against Canonical Entities
        match = process.extractOne(
            raw_name,
            self.canonical_entities,
            scorer=fuzz.token_sort_ratio
        )

        if match:
            best_canonical, score, index = match
            if score >= self.fuzzy_threshold:
                logger.info(
                    f"Resolved '{raw_name}' -> '{best_canonical}' (score: {score:.1f})",
                    extra={"component": "EntityResolver"}
                )
                res = EntityResolutionResult(raw_name, best_canonical, "FUZZY", score, source_url, now_iso)
                self.resolution_logs.append(res)
                return res

        # 4. Fallback: Keep clean normalized form as unresolved (avoid false merge!)
        fallback_name = raw_name.strip()
        logger.info(f"Entity '{raw_name}' unresolved (below {self.fuzzy_threshold}% threshold)", extra={"component": "EntityResolver"})
        res = EntityResolutionResult(raw_name, fallback_name, "UNRESOLVED", score if match else 0.0, source_url, now_iso)
        self.resolution_logs.append(res)
        return res
