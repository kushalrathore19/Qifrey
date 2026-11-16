"""Parse raw .txt manuscript into chapters."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

# Roman numeral map for converting to int
_ROMAN_MAP: dict[str, int] = {
    "I": 1,
    "IV": 4,
    "V": 5,
    "IX": 9,
    "X": 10,
    "XL": 40,
    "L": 50,
    "XC": 90,
    "C": 100,
    "CD": 400,
    "D": 500,
    "CM": 900,
    "M": 1000,
}

_WORD_TO_NUM: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "twenty-one": 21,
    "twenty-two": 22,
    "twenty-three": 23,
    "twenty-four": 24,
    "twenty-five": 25,
    "twenty-six": 26,
    "twenty-seven": 27,
    "twenty-eight": 28,
    "twenty-nine": 29,
    "thirty": 30,
    "thirty-one": 31,
    "thirty-two": 32,
    "thirty-three": 33,
    "thirty-four": 34,
    "thirty-five": 35,
    "thirty-six": 36,
    "thirty-seven": 37,
    "thirty-eight": 38,
    "thirty-nine": 39,
    "forty": 40,
    "forty-one": 41,
    "forty-two": 42,
    "forty-three": 43,
    "forty-four": 44,
    "forty-five": 45,
    "forty-six": 46,
    "forty-seven": 47,
    "forty-eight": 48,
    "forty-nine": 49,
    "fifty": 50,
}


@dataclass
class ParsedChapter:
    """A chapter extracted from a manuscript."""

    index: int
    title: str
    text: str
    content_hash: str


def _roman_to_int(s: str) -> int | None:
    """Convert a roman numeral string to int, or None if invalid."""
    s = s.upper().strip()
    if not s or not re.fullmatch(r"[IVXLCDM]+", s):
        return None
    result = 0
    i = 0
    ordered = sorted(_ROMAN_MAP.items(), key=lambda x: x[1], reverse=True)
    while i < len(s):
        for symbol, value in ordered:
            if s[i:].startswith(symbol):
                result += value
                i += len(symbol)
                break
        else:
            return None
    return result


def _content_hash(text: str) -> str:
    """Compute SHA-256 hex digest of text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _strip_gutenberg(text: str) -> str:
    """Remove Project Gutenberg header and footer."""
    lines = text.split("\n")
    start_idx = 0
    end_idx = len(lines)

    for i, line in enumerate(lines):
        if "*** START OF" in line.upper() or "***START OF" in line.upper():
            start_idx = i + 1
            break

    for i in range(len(lines) - 1, -1, -1):
        if "*** END OF" in lines[i].upper() or "***END OF" in lines[i].upper():
            end_idx = i
            break

    return "\n".join(lines[start_idx:end_idx])


# Pattern to match chapter headings.
# Matches lines like:
#   Chapter 1, Chapter 1: Title, CHAPTER IV, Chapter One, Part II
_CHAPTER_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:chapter|part)\s+"
    r"(?:"
    r"(\d+)"  # Arabic number
    r"|([IVXLCDM]+)"  # Roman numeral
    r"|([a-zA-Z][\w-]*)"  # Word number (one, two, ...)
    r")"
    r"(?:\s*[:.—–-]\s*(.*))?"  # Optional subtitle after : or . or dash
    r")"
    r"\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _detect_chapters(text: str) -> list[tuple[int, str, int]]:
    """Find chapter headings. Returns list of (chapter_number, title, char_position)."""
    results: list[tuple[int, str, int]] = []

    for match in _CHAPTER_PATTERN.finditer(text):
        arabic, roman, word = match.group(1), match.group(2), match.group(3)
        subtitle = (match.group(4) or "").strip()

        if arabic:
            num = int(arabic)
        elif roman:
            num_val = _roman_to_int(roman)
            if num_val is None:
                continue
            num = num_val
        elif word:
            num_val = _WORD_TO_NUM.get(word.lower())
            if num_val is None:
                continue
            num = num_val
        else:
            continue

        full_title = match.group(0).strip()
        if subtitle:
            # Use "Chapter N: Subtitle" format
            prefix = (
                full_title[: full_title.lower().index(subtitle.lower())].strip().rstrip(":.-–—")
            )
            full_title = f"{prefix.strip()}: {subtitle}"

        results.append((num, full_title, match.start()))

    return results


def _split_by_word_count(text: str, words_per_section: int = 3000) -> list[ParsedChapter]:
    """Fallback: split into ~3000-word sections."""
    words = text.split()
    if not words:
        return [ParsedChapter(index=1, title="Section 1", text="", content_hash=_content_hash(""))]

    chapters: list[ParsedChapter] = []
    section_num = 1

    for i in range(0, len(words), words_per_section):
        chunk_words = words[i : i + words_per_section]
        chunk_text = " ".join(chunk_words).strip()
        chapters.append(
            ParsedChapter(
                index=section_num,
                title=f"Section {section_num}",
                text=chunk_text,
                content_hash=_content_hash(chunk_text),
            )
        )
        section_num += 1

    return chapters


def parse_chapters(raw_text: str) -> list[ParsedChapter]:
    """Parse a raw .txt manuscript into chapters.

    1. Strip Project Gutenberg header/footer.
    2. Detect chapter headings (Chapter 1, CHAPTER IV, Chapter One, Part II, etc.).
    3. Fallback: split into ~3000-word sections if no headings found.
    4. Compute SHA-256 content_hash per chapter.
    """
    text = _strip_gutenberg(raw_text)

    headings = _detect_chapters(text)

    if not headings:
        return _split_by_word_count(text)

    chapters: list[ParsedChapter] = []

    for i, (num, title, start_pos) in enumerate(headings):
        # Text starts after the heading line
        heading_end = text.index("\n", start_pos) + 1 if "\n" in text[start_pos:] else len(text)

        end_pos = headings[i + 1][2] if i + 1 < len(headings) else len(text)
        chapter_text = text[heading_end:end_pos].strip()

        chapters.append(
            ParsedChapter(
                index=num,
                title=title,
                text=chapter_text,
                content_hash=_content_hash(chapter_text),
            )
        )

    return chapters


def decode_upload(raw_bytes: bytes) -> str:
    """Decode uploaded bytes as UTF-8, falling back to latin-1."""
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return raw_bytes.decode("latin-1")
