"""Enums for schema validation."""
from enum import Enum

class PricingType(str, Enum):
    FREE = "FREE"
    FREEMIUM = "FREEMIUM"
    PAID = "PAID"
    ENTERPRISE = "ENTERPRISE"
    UNKNOWN = "UNKNOWN"

class RoleFamily(str, Enum):
    ENGINEERING = "ENGINEERING"
    RESEARCH = "RESEARCH"
    PRODUCT = "PRODUCT"
    DATA_AI = "DATA_AI"
    SALES_MARKETING = "SALES_MARKETING"
    OTHER = "OTHER"

class RecordType(str, Enum):
    STARTUP = "STARTUP"
    PRODUCT = "PRODUCT"
    RESEARCH_PAPER = "RESEARCH_PAPER"
    JOB = "JOB"
    NEWS = "NEWS"
