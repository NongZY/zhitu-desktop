"""Restore an approved PostgreSQL custom backup into a NEW local SQLite database.

Does not connect to Docker or execute SQL from the dump. Copies all mapped columns,
verifies every row, checks references, and only then publishes the destination.
Run with backend/.venv Python; install the optional [migration] dependency first.
"""

from __future__ import annotations

import argparse
import enum
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, create_engine, select

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app import models  # noqa: E402, F401
from app.database import Base  # noqa: E402
from app.services.schema_upgrades import READING_TABLE_NAMES  # noqa: E402


def validate_table_names(names: set[str]) -> None:
    expected = set(Base.metadata.tables)
    if names - expected or (expected - names) - READING_TABLE_NAMES:
        raise ValueError("备份中的数据表与当前项目不一致，停止迁移以防遗漏")


def complete_legacy_tables(data: dict) -> dict:
    validate_table_names(set(data))
    complete = {**data}
    for name in READING_TABLE_NAMES:
        complete.setdefault(name, [])
    return complete


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def convert_value(column, value):
    if value is None:
        return None
    if isinstance(column.type, JSON):
        return json.loads(value)
    if isinstance(column.type, Boolean):
        if value not in {"t", "f"}:
            raise ValueError("无法识别的布尔字段")
        return value == "t"
    if isinstance(column.type, Integer):
        return int(value)
    if isinstance(column.type, Float):
        return float(value)
    if isinstance(column.type, DateTime):
        stamp = datetime.fromisoformat(value)
        return stamp.astimezone(timezone.utc).replace(tzinfo=None) if stamp.tzinfo else stamp
    return value


def load_dump(path: Path) -> dict[str, list[dict]]:
    import pgdumplib

    dump = pgdumplib.load(path)
    entries = [entry for entry in dump.entries if entry.desc == "TABLE DATA"]
    names = {entry.tag for entry in entries}
    validate_table_names(names)
    if len(names) != len(entries):
        raise ValueError("备份包含重复的数据表")
    data = {}
    for entry in entries:
        table = Base.metadata.tables[entry.tag]
        match = re.fullmatch(r'COPY public\.(\w+) \(([^)]+)\) FROM stdin;\s*', entry.copy_stmt)
        if entry.namespace != "public" or not match or match[1] != table.name:
            raise ValueError("备份格式无法安全识别")
        names = [name.strip().strip('"') for name in match[2].split(",")]
        if set(names) != set(table.columns.keys()) or len(names) != len(table.columns):
            raise ValueError(f"数据表 {table.name} 的字段与当前项目不一致")
        rows = []
        for values in dump.table_data("public", table.name):
            if len(values) != len(names):
                raise ValueError(f"数据表 {table.name} 有不完整的数据行")
            rows.append({name: convert_value(table.c[name], value)
                         for name, value in zip(names, values, strict=True)})
        data[table.name] = rows
    return complete_legacy_tables(data)


def canonical(value):
    if isinstance(value, datetime):
        return (value.astimezone(timezone.utc).replace(tzinfo=None)
                if value.tzinfo else value).isoformat()
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, dict):
        return {key: canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical(item) for item in value]
    return value


def rows_hash(rows: list[dict]) -> str:
    encoded = sorted(json.dumps(canonical(row), ensure_ascii=False, sort_keys=True)
                     for row in rows)
    return hashlib.sha256("\n".join(encoded).encode("utf-8")).hexdigest()


def write_database(data: dict, target: Path) -> dict:
    target = target.resolve()
    if target.exists():
        raise FileExistsError("目标数据库已存在，禁止覆盖。请另选一个新目录。")
    data = complete_legacy_tables(data)
    for name, rows in data.items():
        columns = set(Base.metadata.tables[name].columns.keys())
        if any(set(row) != columns for row in rows):
            raise ValueError(f"数据表 {name} 的字段与当前项目不一致")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = target.with_name(f"migration-{uuid4().hex}.db")
    engine = create_engine(f"sqlite:///{stage.as_posix()}")
    try:
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            for table in Base.metadata.sorted_tables:
                if data[table.name]:
                    connection.execute(table.insert(), data[table.name])
            if connection.exec_driver_sql("PRAGMA integrity_check").scalar() != "ok":
                raise ValueError("数据库完整性检查失败")
            if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
                raise ValueError("数据关联检查失败，未生成目标数据库")
            report = {}
            for table in Base.metadata.sorted_tables:
                actual = [dict(row) for row in connection.execute(select(table)).mappings()]
                digest = rows_hash(data[table.name])
                if len(actual) != len(data[table.name]) or rows_hash(actual) != digest:
                    raise ValueError(f"数据表 {table.name} 逐行校验失败")
                report[table.name] = {"count": len(actual), "sha256": digest}
        engine.dispose()
        # An exclusive hard link publishes the verified file without replacing any
        # concurrently-created destination (also supported on Windows NTFS).
        target.hardlink_to(stage)
        return report
    finally:
        engine.dispose()
        stage.unlink(missing_ok=True)


def verify_pdf(data: dict, book_id: int, path: Path) -> dict:
    import pymupdf

    chunks = [row for row in data["document_chunks"] if row["textbook_id"] == book_id]
    digest = file_hash(path)
    known = {row["metadata_json"].get("source_sha256") for row in chunks}
    known.discard(None)
    if known and known != {digest}:
        raise ValueError(f"教材 {book_id} 的原文件指纹不符")
    with pymupdf.open(str(path)) as pdf:
        if pdf.needs_pass:
            raise ValueError("教材文件已加密")
        if max((row["page_number"] or 0 for row in chunks), default=0) > len(pdf):
            raise ValueError(f"教材 {book_id} 的页数与备份不符")
        if not known:
            # Older imports have no source fingerprint: check cover, publication
            # information and another page rather than assuming titles identify a file.
            samples = sorted(chunks, key=lambda row: row["chunk_index"])[:3]
            if len(samples) < 3:
                raise ValueError("缺少核对原文件所需的教材片段")
            for chunk in samples:
                source = re.sub(r"\s", "", pdf[chunk["page_number"] - 1].get_text())
                expected = re.sub(r"\s", "", chunk["content"])
                if expected not in source:
                    raise ValueError(f"教材 {book_id} 的页面内容与备份不符")
        return {"sha256": digest, "pages": len(pdf),
                "matched_by": "sha256" if known else "first_three_chunks_and_page_bounds"}


def migrate(source: Path, target: Path, pdfs: dict[int, Path]) -> dict:
    if target.exists():
        raise FileExistsError("本地数据库已存在，未覆盖任何数据")
    data = load_dump(source)
    required = {book["id"] for book in data["textbooks"] if book["file_path"]}
    if set(pdfs) != required:
        raise ValueError(f"必须为有原文件的教材逐一提供 --pdf，教材编号为：{sorted(required)}")
    report = {"backup": source.name, "backup_sha256": file_hash(source),
              "created_at": datetime.now(timezone.utc).isoformat(), "files": {}}
    copies = []
    published = False
    try:
        for book in data["textbooks"]:
            if book["id"] not in pdfs:
                continue
            original = pdfs[book["id"]].resolve()
            info = verify_pdf(data, book["id"], original)
            destination = target.parent / "uploads" / f"{book['id']}-migrated-{uuid4().hex}.pdf"
            destination.parent.mkdir(parents=True, exist_ok=True)
            with original.open("rb") as src, destination.open("xb") as dst:
                copies.append(destination)
                shutil.copyfileobj(src, dst)
            if file_hash(destination) != info["sha256"]:
                raise ValueError("教材文件复制校验失败")
            book["file_path"] = str(destination.resolve())
            report["files"][str(book["id"])] = info
        report["tables"] = write_database(data, target)
        published = True
        report["database"] = str(target.resolve())
        report["only_data_change"] = "textbooks.file_path mapped to verified local PDF copies"
        report["password_hashes_preserved"] = True
        with (target.parent / f"migration-{uuid4().hex}.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
        return report
    finally:
        if not published:
            for path in copies:
                path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--pdf", action="append", default=[], metavar="BOOK_ID=PDF_PATH")
    args = parser.parse_args()
    pdfs = {}
    for item in args.pdf:
        key, value = item.split("=", 1)
        if int(key) in pdfs:
            parser.error("同一教材编号不能重复指定")
        pdfs[int(key)] = Path(value)
    report = migrate(args.backup.resolve(), args.target.resolve(), pdfs)
    print(json.dumps({"status": "verified", "counts": {
        name: table["count"] for name, table in report["tables"].items()
    }, "password_hashes_preserved": True, "pdf_files": len(report["files"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
