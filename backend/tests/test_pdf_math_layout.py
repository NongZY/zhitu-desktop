"""Mathematical layout is recovered only when the PDF supplies geometric evidence."""

import os
from hashlib import sha256

import pymupdf
import pytest


def identity(character, font_name):
    return character


def test_vector_fraction_keeps_numerator_denominator_and_surrounding_text():
    from app.services.pdf_math_layout import extract_math_layout

    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((40, 102), "q =", fontsize=12)
        page.insert_text((70, 94), "5", fontsize=12)
        page.insert_text((70, 111), "2", fontsize=12)
        page.draw_line((68, 98), (79, 98), width=0.5)
        page.insert_text((85, 102), ", done", fontsize=12)
        text, stats = extract_math_layout(page, identity)

    assert "q = (5)/(2), done" in text
    assert stats["fractions_recovered"] == 1


def test_superscript_requires_small_raised_math_text_adjacent_to_a_math_base():
    from app.services.pdf_math_layout import extract_math_layout

    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((50, 100), "x", fontsize=14)
        page.insert_text((57, 94), "2", fontsize=8)
        page.insert_text((70, 100), "+ 1", fontsize=14)
        page.insert_text((50, 140), "ordinary", fontsize=14)
        page.insert_text((102, 134), "2", fontsize=8)
        text, stats = extract_math_layout(page, identity)
    assert "x^2 + 1" in text
    assert "ordinary^2" not in text
    assert stats["superscripts_recovered"] == 1
    assert stats["layout_warnings"] == []


@pytest.mark.skipif(not os.environ.get("TEXTBOOK_TEST_PDF"), reason="real PDF not supplied")
def test_supplied_textbook_page_17_recovers_fraction_and_nested_parentheses():
    from app.services.pdf_math_layout import extract_math_layout

    # This callback intentionally only handles explicit full-width ASCII here.
    # Document-specific glyph substitutions have their own regression tests.
    def width_only(character, font_name):
        value = ord(character)
        return chr(value - 0xFEE0) if 0xFF01 <= value <= 0xFF5E else character

    with pymupdf.open(os.environ["TEXTBOOK_TEST_PDF"]) as document:
        text, stats = extract_math_layout(document[16], width_only)
    compact = "".join(text.split())
    assert "6,-8,-3.9,(5)/(2),-(2)/(11),100,0." in compact
    assert "-(-(3)/(5))" in compact
    assert stats["fractions_recovered"] == 3


@pytest.mark.parametrize("negative", [False, True])
def test_mixed_number_has_explicit_grouping_including_negative_sign(negative):
    from app.services.pdf_math_layout import extract_math_layout

    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((50, 103), "-2" if negative else "2", fontsize=12)
        start = 64 if negative else 60
        page.insert_text((start, 94), "1", fontsize=12)
        page.insert_text((start, 111), "3", fontsize=12)
        page.draw_line((start - 1, 98), (start + 8, 98), width=0.5)
        text, stats = extract_math_layout(page, identity)
    assert text.strip() == ("-(2+(1)/(3))" if negative else "(2+(1)/(3))")
    assert stats["fractions_recovered"] == 1


def test_table_cells_and_plain_lines_do_not_turn_into_fractions():
    from app.services.pdf_math_layout import extract_math_layout

    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((50, 60), "First paragraph", fontsize=12)
        page.insert_text((50, 78), "Second line", fontsize=12)
        page.insert_text((70, 124), "5", fontsize=12)
        page.insert_text((70, 141), "2", fontsize=12)
        page.draw_line((60, 128), (85, 128), width=0.5)
        page.draw_line((60, 110), (60, 150), width=0.5)
        page.draw_line((85, 110), (85, 150), width=0.5)
        page.insert_text((120, 124), "5", fontsize=12)
        page.insert_text((120, 141), "2", fontsize=12)
        text, stats = extract_math_layout(page, identity)
    assert "First paragraph\nSecond line" in text
    assert "(5)/(2)" not in text
    assert stats["fractions_recovered"] == 0


def test_nested_fraction_is_flagged_without_partially_inventing_an_expression():
    from app.services.pdf_math_layout import extract_math_layout

    with pymupdf.open() as document:
        page = document.new_page()
        for y, value in [(102, "1"), (116, "2"), (135, "3")]:
            page.insert_text((70, y), value, fontsize=12)
        page.draw_line((69, 106), (78, 106), width=0.5)
        page.draw_line((67, 122), (80, 122), width=0.5)
        text, stats = extract_math_layout(page, identity)
    assert "/" not in text
    assert stats["fractions_recovered"] == 0
    assert "complex_fraction_layout" in stats["layout_warnings"]


def test_raised_symbols_inside_a_fraction_are_not_reassigned_to_the_whole_fraction():
    from app.services.pdf_math_layout import extract_math_layout

    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((70, 94), "x", fontsize=12)
        page.insert_text((76, 89), "2", fontsize=7)
        page.insert_text((73, 111), "3", fontsize=12)
        page.draw_line((68, 98), (82, 98), width=0.5)
        text, stats = extract_math_layout(page, identity)
    assert "/" not in text
    assert stats["fractions_recovered"] == 0
    assert "complex_fraction_layout" in stats["layout_warnings"]


@pytest.mark.skipif(not os.environ.get("TEXTBOOK_TEST_PDF"), reason="real PDF not supplied")
def test_supplied_textbook_page_78_attaches_exponent_to_variable_after_coefficient():
    from app.services.pdf_math_layout import extract_math_layout
    from app.services.pdf_symbols import PdfSymbolNormalizer

    path = os.environ["TEXTBOOK_TEST_PDF"]
    with open(path, "rb") as source:
        digest = sha256(source.read()).hexdigest()
    with pymupdf.open(path) as document:
        text, stats = extract_math_layout(document[77], PdfSymbolNormalizer(document, digest))
    assert text.count("2x^2+3y") == 3
    assert "2^2x" not in text
    assert stats["superscripts_recovered"] >= 3
