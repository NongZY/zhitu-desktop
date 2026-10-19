"""Regression examples verified against the supplied PDF's rendered page 17."""
import os
from hashlib import sha256

import pymupdf
import pytest


@pytest.mark.skipif(not os.environ.get('TEXTBOOK_TEST_PDF'), reason='real PDF not supplied')
def test_real_book_math_letters_are_not_chinese_characters():
    # Import here so the initial test fails explicitly until the repair exists.
    from app.services.pdf_symbols import PdfSymbolNormalizer

    path = os.environ['TEXTBOOK_TEST_PDF']
    with open(path, 'rb') as source:
        digest = sha256(source.read()).hexdigest()
    with pymupdf.open(path) as doc:
        normalizer = PdfSymbolNormalizer(doc, digest)
        spans = [s for b in doc[16].get_text('dict')['blocks'] if 'lines' in b
                 for line in b['lines'] for s in line['spans']]
        text = ''.join(normalizer(char, span['font']) for span in spans for char in span['text'])
        assert '设a是一个正数' in text
        assert '犪' not in text
        assert normalizer.replacements > 0


def test_chinese_text_and_unverified_documents_are_not_blindly_replaced():
    from app.services.pdf_symbols import PdfSymbolNormalizer

    with pymupdf.open() as doc:
        normalizer = PdfSymbolNormalizer(doc, 'unrecognized-document')
        assert normalizer('犪', 'ChineseFont') == '犪'
        assert normalizer('犪', 'E-BX9-PK748a0') == '犪'
        assert normalizer('\x00', 'ChineseFont') == '�'
        assert normalizer('\ue012', 'UnknownFont') == '�'
        assert normalizer('²', 'MathFont') == '²'
        assert normalizer('５', 'MathFont') == '5'
