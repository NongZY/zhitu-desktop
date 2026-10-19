"""Conservative character decoding, with a narrowly scoped verified font profile.

Some legacy PDFs have correct drawn glyphs but incorrect ToUnicode tables. Never
replace Chinese letters globally: this profile applies only to the exact audited
book and its E-BX9 math font/CID encoding. Other files keep their ordinary text.
"""
from __future__ import annotations

import re

AUDITED_BOOK_SHA256 = 'cb14b1c61bc4f85e42f714073f67eedd9cfeaacc28bc663b3d68b19b4e8df58a'
EXTRACTION_VERSION = 'math-layout-v1'


class PdfSymbolNormalizer:
    def __init__(self, document, source_sha256: str):
        self.verified_profile = source_sha256 == AUDITED_BOOK_SHA256
        self.maps: dict[str, dict[str, str]] = {}
        self.replacements = 0
        self.unknown_symbols = 0
        if not self.verified_profile:
            return
        seen: set[int] = set()
        for page in document:
            for font in page.get_fonts():
                xref, name = font[0], font[3]
                if xref in seen or not name.startswith('E-BX9-PK748'):
                    continue
                seen.add(xref)
                kind, value = document.xref_get_key(xref, 'ToUnicode')
                if kind != 'xref':
                    continue
                stream = document.xref_stream(int(value.split()[0])).decode('latin1')
                mapping = self.maps.setdefault(name.removesuffix('-Identity-H'), {})
                # Audited publisher encoding uses CID = ASCII + 1 for italic Latin.
                # Only single-codepoint CJK mis-mappings are eligible, not numbers,
                # punctuation, Unicode mathematical alphabets or arbitrary ranges.
                for first, last, target in re.findall(
                    r'<([0-9a-fA-F]{4})>\s*<([0-9a-fA-F]{4})>\s*<([0-9a-fA-F]{4})>',
                    stream,
                ):
                    cid, end, codepoint = int(first, 16), int(last, 16), int(target, 16)
                    if cid == end and 0x7280 <= codepoint <= 0x7300 and (
                        0x42 <= cid <= 0x5B or 0x62 <= cid <= 0x7B
                    ):
                        mapping[chr(codepoint)] = chr(cid - 1)

    def __call__(self, char: str, font: str) -> str:
        repaired = self.maps.get(font, {}).get(char)
        if self.verified_profile and char == '\ue011' and font.startswith('E-'):
            repaired = '-'
        if self.verified_profile and char == '\ue012' and font.startswith('O9-PK748'):
            repaired = '*'
        if repaired is not None:
            self.replacements += 1
            return repaired
        if char == '\x00' or char == '\ufffd' or 0xE000 <= ord(char) <= 0xF8FF:
            self.unknown_symbols += 1
            return '\ufffd'
        # Width normalization preserves meaning; NFKC is deliberately avoided as
        # it would flatten superscripts such as ² into ordinary digits.
        if 0xFF01 <= ord(char) <= 0xFF5E:
            return chr(ord(char) - 0xFEE0)
        if char == '\u3000':
            return ' '
        return char
