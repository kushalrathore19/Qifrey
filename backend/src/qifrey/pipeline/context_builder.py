"""Context and memory builder for LLM extraction."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from qifrey.db.models import Character


def estimate_tokens(text: str) -> int:
    """Rough token estimation (approx 4 chars per token for English text)."""
    return max(1, len(text) // 4)


def chunk_chapter_text(text: str, max_words: int = 3000) -> list[str]:
    """Split chapter text into chunks of at most ~max_words along paragraph boundaries."""
    words = text.split()
    if len(words) <= max_words:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_word_count = 0

    for para in paragraphs:
        para_words = len(para.split())
        if current_word_count + para_words > max_words and current_chunk:
            chunks.append("\n\n".join(current_chunk).strip())
            current_chunk = [para]
            current_word_count = para_words
        else:
            current_chunk.append(para)
            current_word_count += para_words

    if current_chunk:
        chunks.append("\n\n".join(current_chunk).strip())

    return chunks if chunks else [text]


def scan_known_characters(text: str, characters: list[Character]) -> list[Character]:
    """Scan text for known canonical names and aliases using whole-word matching."""
    text_lower = text.lower()
    matched: list[Character] = []

    for char in characters:
        names_to_check = [char.canonical_name] + [a.name for a in char.aliases]
        for name in names_to_check:
            clean_name = name.strip().lower()
            if not clean_name:
                continue
            # Regex word boundary check if word is alphanumeric
            pattern = rf"\b{re.escape(clean_name)}\b"
            if re.search(pattern, text_lower):
                matched.append(char)
                break

    return matched


def build_memory_block(
    story_id: int,
    chapter_index: int,
    text: str,
    db: Session,
    max_tokens: int = 1500,
) -> str:
    """Build a compact memory block for the LLM prompt.

    Chapter 1 starts with an empty memory block.
    For later chapters, lists all canonical characters/aliases, plus top facts for
    characters appearing in this chapter, capped by max_tokens.
    """
    if chapter_index <= 1:
        return ""

    from qifrey.db.models import Character, Fact

    characters = (
        db.query(Character)
        .filter(Character.story_id == story_id)
        .order_by(Character.canonical_name)
        .all()
    )

    if not characters:
        return ""

    appearing_characters = scan_known_characters(text, characters)

    lines: list[str] = [
        "### KNOWN CHARACTERS & MEMORY (Reuse canonical names when aliases appear):"
    ]

    # 1. Roster of all characters and known aliases
    lines.append("ROSTER:")
    for char in characters:
        aliases_str = ", ".join(
            f'"{a.name}"' for a in char.aliases if a.name != char.canonical_name
        )
        if aliases_str:
            lines.append(f"- {char.canonical_name} (aliases: {aliases_str})")
        else:
            lines.append(f"- {char.canonical_name}")

    # 2. Known facts for appearing characters
    if appearing_characters:
        lines.append("\nESTABLISHED FACTS FOR CHARACTERS IN THIS CHAPTER:")
        for char in appearing_characters:
            char_facts = (
                db.query(Fact)
                .filter(Fact.character_id == char.id)
                .order_by(Fact.confidence.desc())
                .limit(8)
                .all()
            )
            if char_facts:
                lines.append(f"• {char.canonical_name}:")
                for f in char_facts:
                    lines.append(f"   - {f.attribute}: {f.value}")

    raw_block = "\n".join(lines)

    # Cap size if it exceeds max_tokens
    if estimate_tokens(raw_block) > max_tokens:
        char_limit = max_tokens * 4
        truncated = raw_block[:char_limit]
        last_newline = truncated.rfind("\n")
        if last_newline != -1:
            truncated = truncated[:last_newline]
        return truncated + "\n...[memory truncated to fit limit]"

    return raw_block
