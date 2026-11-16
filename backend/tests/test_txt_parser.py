"""Tests for the .txt manuscript parser."""

from __future__ import annotations

from qifrey.ingestion.txt_parser import _strip_gutenberg, decode_upload, parse_chapters

SAMPLE_WITH_GUTENBERG = """
The Project Gutenberg eBook of Test Story

*** START OF THE PROJECT GUTENBERG EBOOK TEST STORY ***

Chapter I: The Beginning

Once upon a time in a land far away, there lived a young wizard named Qifrey.
He had bright blue eyes and a mysterious past that no one dared to ask about.

Chapter II

The second chapter continues the tale. Qifrey traveled through many lands,
meeting characters of all sorts. His companion was a young apprentice named Coco.

Chapter III: The Final Act

In the end, all was revealed. The magic was real, and the contradictions
in the story were finally resolved by the great author.

*** END OF THE PROJECT GUTENBERG EBOOK TEST STORY ***

End of the Project Gutenberg EBook
"""


SAMPLE_ROMAN_NUMERALS = """Chapter IV: The Return

The hero returned to the village after many years.

Chapter V

A new adventure began.

Chapter VI: Epilogue

And they lived happily ever after.
"""


SAMPLE_WORD_NUMBERS = """Chapter One: Dawn

The sun rose over the mountains.

Chapter Two

Rain began to fall.

Chapter Three: Dusk

The sun set behind the hills.
"""


SAMPLE_NO_CHAPTERS = "This is just a plain text without any chapter headings. " + "word " * 100


class TestStripGutenberg:
    def test_strips_header_and_footer(self) -> None:
        result = _strip_gutenberg(SAMPLE_WITH_GUTENBERG)
        assert "Project Gutenberg eBook" not in result
        assert "*** START OF" not in result.upper()
        assert "*** END OF" not in result.upper()
        assert "Chapter I" in result

    def test_no_gutenberg_markers(self) -> None:
        text = "Chapter 1\n\nSome text here."
        result = _strip_gutenberg(text)
        assert result == text


class TestParseChapters:
    def test_three_chapters_with_gutenberg(self) -> None:
        chapters = parse_chapters(SAMPLE_WITH_GUTENBERG)
        assert len(chapters) == 3
        assert chapters[0].index == 1
        assert chapters[1].index == 2
        assert chapters[2].index == 3
        assert "Qifrey" in chapters[0].text
        assert "Coco" in chapters[1].text
        assert "contradictions" in chapters[2].text

    def test_roman_numerals(self) -> None:
        chapters = parse_chapters(SAMPLE_ROMAN_NUMERALS)
        assert len(chapters) == 3
        assert chapters[0].index == 4
        assert chapters[1].index == 5
        assert chapters[2].index == 6

    def test_word_numbers(self) -> None:
        chapters = parse_chapters(SAMPLE_WORD_NUMBERS)
        assert len(chapters) == 3
        assert chapters[0].index == 1
        assert chapters[1].index == 2
        assert chapters[2].index == 3

    def test_content_hash_is_sha256(self) -> None:
        chapters = parse_chapters(SAMPLE_WITH_GUTENBERG)
        for ch in chapters:
            assert len(ch.content_hash) == 64  # SHA-256 hex length

    def test_content_hash_changes_with_content(self) -> None:
        chapters = parse_chapters(SAMPLE_WITH_GUTENBERG)
        hashes = [ch.content_hash for ch in chapters]
        assert len(set(hashes)) == len(hashes)  # All different

    def test_fallback_sections(self) -> None:
        chapters = parse_chapters(SAMPLE_NO_CHAPTERS)
        assert len(chapters) >= 1
        assert chapters[0].title.startswith("Section")

    def test_chapter_titles_preserved(self) -> None:
        chapters = parse_chapters(SAMPLE_WITH_GUTENBERG)
        assert "Beginning" in chapters[0].title
        assert "Final" in chapters[2].title


class TestDecodeUpload:
    def test_utf8(self) -> None:
        text = "Hello café"
        assert decode_upload(text.encode("utf-8")) == text

    def test_latin1_fallback(self) -> None:
        text = "Hello café"
        raw = text.encode("latin-1")
        result = decode_upload(raw)
        assert "caf" in result
