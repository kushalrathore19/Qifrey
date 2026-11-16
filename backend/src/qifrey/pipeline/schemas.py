"""Pydantic schemas for LLM extraction and validation."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

CONTROLLED_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "eye_color",
        "hair_color",
        "skin_tone",
        "age",
        "height",
        "weight",
        "build",
        "gender",
        "occupation",
        "title",
        "clothing",
        "marital_status",
        "nationality",
        "birthplace",
        "home_location",
        "vehicle_color",
        "vehicle_type",
        "personality",
        "skill",
        "affiliation",
        "weapon",
        "pet",
        "voice",
        "wound_or_scar",
    }
)


class CharacterExtraction(BaseModel):
    """Extracted character information."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Canonical or prominent name of the character")
    aliases: list[str] = Field(
        default_factory=list, description="Other names or titles used for this character"
    )
    description: str | None = Field(default=None, description="Brief description of the character")
    evidence_quote: str | None = Field(
        default=None, description="Verbatim text quote mentioning the character"
    )


class LocationExtraction(BaseModel):
    """Extracted location information."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Name of the place, building, city, or realm")
    description: str | None = Field(default=None, description="Brief description of the location")


class FactExtraction(BaseModel):
    """Extracted fact about a character."""

    model_config = ConfigDict(extra="ignore")

    character: str = Field(..., description="Name of the character this fact describes")
    attribute: str = Field(
        ...,
        description="Controlled attribute name (e.g., eye_color, age) or other:<snake_case>",
    )
    value: str = Field(..., description="The value of the attribute, e.g., 'blue', '34 years old'")
    evidence_quote: str = Field(
        ..., description="Verbatim quote from chapter text proving this fact"
    )
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0"
    )

    @field_validator("attribute")
    @classmethod
    def validate_and_normalize_attribute(cls, v: str) -> str:
        cleaned = v.strip().lower().replace(" ", "_").replace("-", "_")
        if cleaned in CONTROLLED_ATTRIBUTES:
            return cleaned
        if cleaned.startswith("other:"):
            rest = cleaned[len("other:") :]
            if re.fullmatch(r"[a-z0-9_]+", rest):
                return cleaned
            raise ValueError(f"Invalid other:<snake_case> attribute: {v!r}")
        if re.fullmatch(r"[a-z0-9_]+", cleaned):
            return f"other:{cleaned}"
        raise ValueError(f"Attribute cannot be normalized to valid format: {v!r}")


class RelationshipExtraction(BaseModel):
    """Extracted relationship between two characters."""

    model_config = ConfigDict(extra="ignore")

    a: str = Field(..., description="First character name")
    b: str = Field(..., description="Second character name")
    type: str = Field(
        ..., description="Relationship type, e.g. friend, enemy, sister, apprentice, mentor"
    )
    evidence_quote: str | None = Field(
        default=None, description="Verbatim quote proving this relationship"
    )


class ExtractionOutput(BaseModel):
    """Top-level schema for chapter extraction."""

    model_config = ConfigDict(extra="ignore")

    characters: list[CharacterExtraction] = Field(default_factory=list)
    locations: list[LocationExtraction] = Field(default_factory=list)
    facts: list[FactExtraction] = Field(default_factory=list)
    relationships: list[RelationshipExtraction] = Field(default_factory=list)


class AliasResolutionOutput(BaseModel):
    """Result of an LLM query resolving ambiguous character aliases."""

    model_config = ConfigDict(extra="ignore")

    is_same_person: bool = Field(description="True if the two names refer to the same person")
    canonical_name: str = Field(description="The preferred canonical name to use")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    explanation: str = Field(default="", description="Reasoning behind the decision")


class ValidationResult(BaseModel):
    """Result of validating an extraction."""

    accepted_characters: list[CharacterExtraction] = Field(default_factory=list)
    accepted_locations: list[LocationExtraction] = Field(default_factory=list)
    accepted_facts: list[FactExtraction] = Field(default_factory=list)
    accepted_relationships: list[RelationshipExtraction] = Field(default_factory=list)
    rejections: list[dict[str, str]] = Field(default_factory=list)
