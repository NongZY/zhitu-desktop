from pathlib import Path

import pymupdf
import pytest

from app.database import SessionLocal
from app.models import DocumentChunk, Textbook


def _textbook_with_pdf(
    client, headers, tmp_path: Path, page_size: tuple[int, int] = (600, 800),
) -> tuple[int, Path]:
    response = client.post(
        "/api/v1/textbooks",
        headers=headers,
        json={"title": "含公式的个人教材", "subject": "数学"},
    )
    assert response.status_code == 201
    textbook_id = response.json()["id"]
    path = tmp_path / "original.pdf"
    with pymupdf.open() as document:
        first_page = document.new_page(width=page_size[0], height=page_size[1])
        first_page.insert_text((60, 70), "x + 2 = 5", fontsize=24)
        first_page.draw_circle((120, 160), 30, color=(1, 0, 0), fill=(1, 0, 0))
        second_page = document.new_page(width=800, height=600)
        second_page.insert_text((60, 70), "y = x / 2", fontsize=24)
        second_page.draw_rect((90, 120, 150, 180), color=(0, 0, 1), fill=(0, 0, 1))
        document.save(path)
    with SessionLocal() as db:
        textbook = db.get(Textbook, textbook_id)
        textbook.file_path = str(path)
        db.commit()
    return textbook_id, path


def test_owner_can_view_original_pdf_page_as_private_png(client, create_learner, tmp_path):
    owner = create_learner("page-owner@example.com")
    textbook_id, path = _textbook_with_pdf(client, owner, tmp_path)

    response = client.get(
        f"/api/v1/textbooks/{textbook_id}/pages/1/image", headers=owner,
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/png"
    assert "no-store" in response.headers["cache-control"]
    assert "private" in response.headers["cache-control"]
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
    image = pymupdf.Pixmap(response.content)
    assert (image.width, image.height) == (1200, 1600)
    assert image.pixel(240, 320) == (255, 0, 0)
    assert path.exists(), "Local source PDF must remain available"


@pytest.mark.parametrize("page_number", [0, -1, 3])
def test_page_numbers_are_one_based_and_must_exist(
    client, create_learner, tmp_path, page_number,
):
    owner = create_learner("page-owner@example.com")
    textbook_id, _ = _textbook_with_pdf(client, owner, tmp_path)

    response = client.get(
        f"/api/v1/textbooks/{textbook_id}/pages/{page_number}/image", headers=owner,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "原页不存在"


def test_large_pages_are_scaled_to_at_most_2000_pixels(client, create_learner, tmp_path):
    owner = create_learner("page-owner@example.com")
    textbook_id, _ = _textbook_with_pdf(client, owner, tmp_path, page_size=(1100, 1500))

    response = client.get(
        f"/api/v1/textbooks/{textbook_id}/pages/1/image", headers=owner,
    )

    assert response.status_code == 200
    image = pymupdf.Pixmap(response.content)
    assert max(image.width, image.height) <= 2000


@pytest.mark.parametrize(
    ("source_state", "expected_status"),
    [("missing_attachment", 404), ("missing_file", 404), ("invalid_pdf", 422)],
)
def test_unavailable_original_has_a_safe_error(
    client, create_learner, tmp_path, source_state, expected_status,
):
    owner = create_learner("page-owner@example.com")
    textbook_id, path = _textbook_with_pdf(client, owner, tmp_path)
    if source_state == "missing_attachment":
        with SessionLocal() as db:
            db.get(Textbook, textbook_id).file_path = None
            db.commit()
    elif source_state == "missing_file":
        path.unlink()
    else:
        path.write_bytes(b"not a PDF")

    response = client.get(
        f"/api/v1/textbooks/{textbook_id}/pages/1/image", headers=owner,
    )

    assert response.status_code == expected_status
    assert str(tmp_path) not in response.text
    assert response.json()["detail"] in {"教材原文件不存在", "原页暂时无法读取，请检查 PDF 后重试"}


def test_original_pages_require_login_and_textbook_ownership(client, create_learner, tmp_path):
    owner = create_learner("page-owner@example.com")
    visitor = create_learner("page-visitor@example.com")
    textbook_id, _ = _textbook_with_pdf(client, owner, tmp_path)
    path = f"/api/v1/textbooks/{textbook_id}/pages/1/image"

    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer invalid"}).status_code == 401
    forbidden = client.get(path, headers=visitor)
    missing = client.get("/api/v1/textbooks/999999/pages/1/image", headers=owner)
    assert forbidden.status_code == missing.status_code == 404
    assert forbidden.json() == missing.json() == {"detail": "教材不存在"}


def test_second_page_uses_pdf_page_number_not_textbook_printed_number(
    client, create_learner, tmp_path,
):
    owner = create_learner("page-owner@example.com")
    textbook_id, _ = _textbook_with_pdf(client, owner, tmp_path)

    response = client.get(
        f"/api/v1/textbooks/{textbook_id}/pages/2/image", headers=owner,
    )

    assert response.status_code == 200
    image = pymupdf.Pixmap(response.content)
    assert (image.width, image.height) == (1600, 1200)
    assert image.pixel(240, 300) == (0, 0, 255)


@pytest.mark.parametrize(("page_number", "corrupt", "status"), [(1, False, 200), (3, False, 404), (1, True, 422)])
def test_materialized_temporary_pdf_is_removed_after_success_or_error(
    client, create_learner, tmp_path, monkeypatch, page_number, corrupt, status,
):
    owner = create_learner("page-owner@example.com")
    textbook_id, source_path = _textbook_with_pdf(client, owner, tmp_path)
    temporary_path = tmp_path / "materialized.pdf"
    temporary_path.write_bytes(b"broken PDF" if corrupt else source_path.read_bytes())
    with SessionLocal() as db:
        db.get(Textbook, textbook_id).file_path = "minio://private/original.pdf"
        db.commit()

    def materialize(uri):
        assert uri == "minio://private/original.pdf"
        return temporary_path, True

    monkeypatch.setattr("app.api.textbooks.materialize", materialize)
    response = client.get(
        f"/api/v1/textbooks/{textbook_id}/pages/{page_number}/image", headers=owner,
    )

    assert response.status_code == status
    assert not temporary_path.exists()
    assert source_path.exists()


def test_storage_errors_do_not_expose_object_names_or_internal_details(
    client, create_learner, tmp_path, monkeypatch,
):
    owner = create_learner("page-owner@example.com")
    textbook_id, _ = _textbook_with_pdf(client, owner, tmp_path)

    def unavailable_storage(_uri):
        raise RuntimeError("private-storage/object-key: internal connection failure")

    monkeypatch.setattr("app.api.textbooks.materialize", unavailable_storage)
    response = client.get(
        f"/api/v1/textbooks/{textbook_id}/pages/1/image", headers=owner,
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "原页暂时无法读取，请检查 PDF 后重试"}


def test_chapter_content_marks_only_pages_requiring_formula_review(
    client, create_learner, tmp_path,
):
    owner = create_learner("page-owner@example.com")
    textbook_id, _ = _textbook_with_pdf(client, owner, tmp_path)
    chapter = client.post(
        f"/api/v1/textbooks/{textbook_id}/chapters", headers=owner,
        json={"title": "分数与根式"},
    ).json()
    with SessionLocal() as db:
        db.add_all([
            DocumentChunk(
                textbook_id=textbook_id, chapter_id=chapter["id"], page_number=1,
                content="a / b", metadata_json={"math_review_required": True},
            ),
            DocumentChunk(
                textbook_id=textbook_id, chapter_id=chapter["id"], page_number=2,
                content="正常正文", metadata_json={},
            ),
        ])
        db.commit()

    response = client.get(f"/api/v1/chapters/{chapter['id']}/content", headers=owner)

    assert response.status_code == 200
    first, second = response.json()["items"]
    assert first["quality_note"] == "本页有公式或符号需要对照原页，请勿仅凭提取文字计算。"
    assert not second.get("quality_note")
