"""Alias resolver for mapping character names to existing or new entities."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from qifrey.pipeline.llm_client import LLMClient, get_llm_client
from qifrey.pipeline.schemas import AliasResolutionOutput

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from qifrey.db.models import Character

logger = logging.getLogger(__name__)

HONORIFICS: frozenset[str] = frozenset(
    {
        "mr",
        "mrs",
        "miss",
        "ms",
        "dr",
        "prof",
        "professor",
        "detective",
        "inspector",
        "sergeant",
        "captain",
        "officer",
        "lord",
        "lady",
        "sir",
        "father",
        "brother",
        "sister",
        "master",
        "madam",
        "madame",
    }
)

# In-memory resolution cache: (story_id, candidate_name_lower) -> character_id
_RESOLUTION_CACHE: dict[tuple[int, str], int] = {}
# LLM answer cache: (story_id, name_lower, tuple_of_candidate_ids) -> character_id | None
_LLM_RESOLUTION_CACHE: dict[tuple[int, str, tuple[int, ...]], int | None] = {}


def clear_resolution_cache() -> None:
    """Clear in-memory resolution caches (useful for tests)."""
    _RESOLUTION_CACHE.clear()
    _LLM_RESOLUTION_CACHE.clear()


def strip_honorifics(name: str) -> str:
    """Strip common English titles and honorifics from a name."""
    clean = re.sub(r"[^\w\s]", "", name).strip()
    words = clean.split()
    if words and words[0].lower() in HONORIFICS:
        words = words[1:]
    return " ".join(words).strip()


def _tokenize(name: str) -> set[str]:
    clean = re.sub(r"[^\w\s]", "", name.lower())
    return {w for w in clean.split() if w and w not in HONORIFICS}


def _match_exact_or_alias(name: str, characters: list[Character]) -> Character | None:
    norm_name = name.strip().lower()
    for char in characters:
        if char.canonical_name.strip().lower() == norm_name:
            return char
        for a in char.aliases:
            if a.name.strip().lower() == norm_name:
                return char
    return None


def _match_honorific_stripped(name: str, characters: list[Character]) -> Character | None:
    stripped = strip_honorifics(name).lower()
    if not stripped:
        return None
    for char in characters:
        if strip_honorifics(char.canonical_name).lower() == stripped:
            return char
        for a in char.aliases:
            if strip_honorifics(a.name).lower() == stripped:
                return char
    return None


def _match_single_name(name: str, characters: list[Character]) -> list[Character]:
    """Match single-token names (like surname or first name) against characters."""
    stripped = strip_honorifics(name).lower()
    tokens = _tokenize(stripped)
    if len(tokens) != 1:
        return []

    target = next(iter(tokens))
    candidates: list[Character] = []
    for char in characters:
        char_tokens = _tokenize(char.canonical_name)
        for a in char.aliases:
            char_tokens.update(_tokenize(a.name))
        if target in char_tokens:
            candidates.append(char)
    return candidates


def _match_token_subset(name: str, characters: list[Character]) -> list[Character]:
    """Find characters whose name tokens are a superset of the query tokens."""
    tokens = _tokenize(name)
    if not tokens:
        return []

    candidates: list[Character] = []
    for char in characters:
        char_tokens = _tokenize(char.canonical_name)
        for a in char.aliases:
            char_tokens.update(_tokenize(a.name))
        if tokens.issubset(char_tokens):
            candidates.append(char)
    return candidates


def resolve_or_create_character(
    name: str,
    story_id: int,
    db: Session,
    *,
    description: str | None = None,
    llm_client: LLMClient | None = None,
) -> Character | None:
    """Map a mentioned name to an existing Character or create a new one."""
    from qifrey.db.models import Alias, Character, IgnoredName

    clean_name = name.strip()
    if not clean_name:
        clean_name = "Unknown"

    # Check if name is ignored
    ignored = db.query(IgnoredName).filter(IgnoredName.story_id == story_id).all()
    ignored_set = {i.name.strip().lower() for i in ignored}
    if clean_name.lower() in ignored_set or strip_honorifics(clean_name).lower() in ignored_set:
        return None

    cache_key = (story_id, clean_name.lower())
    if cache_key in _RESOLUTION_CACHE:
        cached_id = _RESOLUTION_CACHE[cache_key]
        cached_char = db.query(Character).filter(Character.id == cached_id).first()
        if cached_char:
            if cached_char.status == "planned":
                cached_char.status = "active"
                db.flush()
            return cached_char

    # Fetch all existing characters for this story, prioritize manual characters first
    all_chars = db.query(Character).filter(Character.story_id == story_id).all()
    manual_chars = [c for c in all_chars if c.source == "manual"]
    ai_chars = [c for c in all_chars if c.source != "manual"]
    characters = manual_chars + ai_chars

    # 1. Exact or alias match
    match = _match_exact_or_alias(clean_name, characters)
    if match:
        if match.status == "planned":
            match.status = "active"
            db.flush()
        _RESOLUTION_CACHE[cache_key] = match.id
        return match

    # 2. Honorific stripping match
    match = _match_honorific_stripped(clean_name, characters)
    if match:
        if match.status == "planned":
            match.status = "active"
            db.flush()
        _add_alias_if_missing(db, match, clean_name)
        _RESOLUTION_CACHE[cache_key] = match.id
        return match

    # 3. Surname/first-name match when unambiguous
    single_matches = _match_single_name(clean_name, characters)
    if len(single_matches) == 1:
        match = single_matches[0]
        if match.status == "planned":
            match.status = "active"
            db.flush()
        _add_alias_if_missing(db, match, clean_name)
        _RESOLUTION_CACHE[cache_key] = match.id
        return match

    # 4. Token-subset match when unambiguous
    subset_matches = _match_token_subset(clean_name, characters)
    if len(subset_matches) == 1:
        match = subset_matches[0]
        if match.status == "planned":
            match.status = "active"
            db.flush()
        _add_alias_if_missing(db, match, clean_name)
        _RESOLUTION_CACHE[cache_key] = match.id
        return match

    # 5. Ambiguous resolution via LLM
    ambiguous_candidates = single_matches or subset_matches
    if len(ambiguous_candidates) >= 2:
        client = llm_client or get_llm_client()
        resolved = _ask_llm_resolution(
            clean_name,
            ambiguous_candidates,
            story_id=story_id,
            llm_client=client,
        )
        if resolved:
            if resolved.status == "planned":
                resolved.status = "active"
                db.flush()
            _add_alias_if_missing(db, resolved, clean_name)
            _RESOLUTION_CACHE[cache_key] = resolved.id
            return resolved

    # 6. Nothing matches: create a brand new character
    new_char = Character(
        story_id=story_id,
        canonical_name=clean_name,
        description=description,
    )
    db.add(new_char)
    db.flush()

    # Also add the stripped version as an alias if different
    stripped = strip_honorifics(clean_name)
    if stripped and stripped.lower() != clean_name.lower():
        db.add(Alias(character_id=new_char.id, name=stripped))
        db.flush()

    _RESOLUTION_CACHE[cache_key] = new_char.id
    return new_char


def _add_alias_if_missing(db: Session, char: Character, alias_name: str) -> None:
    from qifrey.db.models import Alias

    norm = alias_name.strip().lower()
    if norm == char.canonical_name.strip().lower():
        return
    for a in char.aliases:
        if a.name.strip().lower() == norm:
            return

    new_alias = Alias(character_id=char.id, name=alias_name.strip())
    db.add(new_alias)
    db.flush()


def _ask_llm_resolution(
    name: str,
    candidates: list[Character],
    *,
    story_id: int,
    llm_client: LLMClient,
) -> Character | None:
    """Prompt the LLM to resolve which candidate character the name refers to, with caching."""
    cand_ids = tuple(sorted(c.id for c in candidates))
    llm_cache_key = (story_id, name.strip().lower(), cand_ids)

    if llm_cache_key in _LLM_RESOLUTION_CACHE:
        cached_char_id = _LLM_RESOLUTION_CACHE[llm_cache_key]
        if cached_char_id is None:
            return None
        for c in candidates:
            if c.id == cached_char_id:
                return c

    system = (
        "You are an expert narrative analyst. Determine if a mentioned name refers to an "
        "existing character from the provided candidate list or represents a distinct person."
    )
    cand_descriptions = "\n".join(
        f"- ID {c.id}: '{c.canonical_name}' (Description: {c.description or 'No description'})"
        for c in candidates[:4]
    )
    user = (
        f"The story mentions: '{name}'.\n"
        f"Candidate characters in the graph:\n{cand_descriptions}\n\n"
        f"Does '{name}' refer to one of these characters? If yes, set is_same_person=true\n"
        f"and canonical_name to the matching character's exact canonical name.\n"
        f"Otherwise set is_same_person=false."
    )

    matching_char: Character | None = None
    try:
        result = llm_client.complete_json(
            system=system,
            user=user,
            schema=AliasResolutionOutput,
            story_id=story_id,
            purpose="alias_resolution",
        )
        if result.is_same_person:
            for c in candidates:
                if c.canonical_name.strip().lower() == result.canonical_name.strip().lower():
                    matching_char = c
                    break
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM alias resolution failed: %s", exc)

    _LLM_RESOLUTION_CACHE[llm_cache_key] = matching_char.id if matching_char else None
    return matching_char
