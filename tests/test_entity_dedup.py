"""Unit tests for EntityResolver and Deduplicator."""
import pytest
from src.entity_resolution.entity_resolver import EntityResolver
from src.entity_resolution.deduplicator import Deduplicator
from src.schemas import Startup, Product, ResearchPaper, Job, News

def test_entity_resolver_exact():
    resolver = EntityResolver()
    res = resolver.resolve("OpenAI", source_url="https://example.com")
    assert res.canonical_name == "OpenAI"
    assert res.match_method == "EXACT"
    assert res.confidence == 100.0

def test_entity_resolver_alias():
    resolver = EntityResolver()
    res = resolver.resolve("HuggingFace", source_url="https://example.com")
    assert res.canonical_name == "Hugging Face"
    assert res.match_method == "ALIAS"
    assert res.confidence == 100.0

def test_entity_resolver_fuzzy():
    resolver = EntityResolver()
    res = resolver.resolve("Stability.ai", source_url="https://example.com")
    assert res.canonical_name == "Stability AI"
    assert res.match_method in ("EXACT", "ALIAS", "FUZZY")
    assert res.confidence >= 85.0

def test_entity_resolver_unresolved_no_false_merge():
    resolver = EntityResolver(fuzzy_threshold=90.0)
    res = resolver.resolve("Unknown Random AI Startup XYZ", source_url="https://example.com")
    assert res.canonical_name == "Unknown Random AI Startup XYZ"
    assert res.match_method == "UNRESOLVED"

def test_deduplicator_filter():
    dedup = Deduplicator()
    
    p1 = Product(name="Claude 3.5", product_url="https://anthropic.com/claude", source_url="https://example.com")
    p2 = Product(name="Claude 3.5", product_url="https://anthropic.com/claude", source_url="https://example.com/2")
    p3 = Product(name="ChatGPT", product_url="https://openai.com/chatgpt", source_url="https://example.com/3")

    unique = dedup.filter_duplicates([p1, p2, p3])
    assert len(unique) == 2
    assert unique[0].name == "Claude 3.5"
    assert unique[1].name == "ChatGPT"
