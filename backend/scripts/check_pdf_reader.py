"""Read-only deployed-reader check for an existing, privately owned textbook.

Run in the backend container with PYTHONPATH=/app. No login credentials or
textbook content are printed, no records are created, and the PDF is not changed.
An optional output directory receives only rendered QA page images.
"""
import argparse
import hashlib
from pathlib import Path

import httpx
import pymupdf
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Chapter, Textbook, User
from app.security import create_access_token
from app.services.storage import materialize


def check(args):
    with SessionLocal() as db:
        book = db.get(Textbook, args.book_id)
        assert book is not None, 'Book does not exist'
        owner = db.get(User, book.owner_id)
        assert owner is not None and book.file_path
        headers = {'Authorization': 'Bearer ' + create_access_token(owner)}
        chapter = db.scalar(select(Chapter).where(
            Chapter.textbook_id == book.id, Chapter.page_start == args.page,
        ).order_by(Chapter.id.desc()))
        assert chapter is not None, 'Expected chapter/page mapping not present'
        visitor = db.scalar(select(User).where(User.id != owner.id))
        visitor_headers = ({'Authorization': 'Bearer ' + create_access_token(visitor)}
                           if visitor else None)
        file_path = book.file_path
        chapter_id = chapter.id

    with httpx.Client(base_url=args.base_url, headers=headers, timeout=60) as site:
        reader = site.get(f'/textbooks/{args.book_id}/reader')
        assert reader.status_code == 200, reader.status_code
        assert reader.json()['page_count'] == args.pages
        assert 'no-store' in reader.headers.get('cache-control', '')
        for params in ({'q': args.query}, {'q': args.query, 'chapter_id': chapter_id}):
            search = site.get(f'/textbooks/{args.book_id}/search', params=params)
            assert search.status_code == 200, search.status_code
            assert args.page in [hit['page_number'] for hit in search.json()['items']]
        print('LIVE_METADATA_CHAPTER_AND_SEARCH=PASS')

        path, temporary = materialize(file_path)
        try:
            source_bytes = path.read_bytes()
            if args.sha256:
                assert hashlib.sha256(source_bytes).hexdigest() == args.sha256
            with pymupdf.open(stream=source_bytes, filetype='pdf') as pdf:
                for number in (args.page, args.formula_page):
                    response = site.get(f'/textbooks/{args.book_id}/pages/{number}/image')
                    assert response.status_code == 200, response.status_code
                    assert response.headers['content-type'] == 'image/png'
                    assert 'no-store' in response.headers.get('cache-control', '')
                    page = pdf[number - 1]
                    scale = min(2.0, 2000 / max(page.rect.width, page.rect.height))
                    expected = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale),
                                              colorspace=pymupdf.csRGB, alpha=False)
                    actual = pymupdf.Pixmap(response.content)
                    assert actual.samples == expected.samples
                    assert max(actual.width, actual.height) <= 2000
                    if args.output_dir:
                        output = Path(args.output_dir)
                        output.mkdir(parents=True, exist_ok=True)
                        actual.save(output / f'reader-page-{number}.png')
            print('LIVE_ORIGINAL_PAGE_PIXELS_AND_SOURCE_HASH=PASS')
        finally:
            if temporary:
                path.unlink(missing_ok=True)

        bad_page = site.get(f'/textbooks/{args.book_id}/pages/{args.pages + 1}/image')
        assert bad_page.status_code == 404

    with httpx.Client(base_url=args.base_url, timeout=60) as anonymous:
        for route in ('reader', 'search?q=test', f'pages/{args.page}/image'):
            response = anonymous.get(f'/textbooks/{args.book_id}/{route}')
            assert response.status_code in (401, 403)
            if visitor_headers:
                response = anonymous.get(f'/textbooks/{args.book_id}/{route}',
                                         headers=visitor_headers)
                assert response.status_code == 404
    print('LIVE_PAGE_BOUNDS_AND_OWNER_ISOLATION=PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('book_id', type=int)
    parser.add_argument('--base-url', default='http://frontend/api/v1')
    parser.add_argument('--pages', type=int, required=True)
    parser.add_argument('--page', type=int, required=True)
    parser.add_argument('--formula-page', type=int, required=True)
    parser.add_argument('--query', required=True)
    parser.add_argument('--sha256')
    parser.add_argument('--output-dir')
    check(parser.parse_args())
