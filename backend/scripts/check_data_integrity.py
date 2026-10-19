"""Read-only data fingerprint. Prints row counts and hashes, never row contents."""

import hashlib
import json

from sqlalchemy import select

from app import models  # noqa: F401 -- register the application's tables
from app.database import Base, engine


def fingerprints(connection):
    result = {}
    for table in Base.metadata.sorted_tables:
        rows = connection.execute(select(table).order_by(*table.primary_key.columns)).mappings()
        digest = hashlib.sha256()
        count = 0
        for row in rows:
            digest.update(
                json.dumps(dict(row), sort_keys=True, default=str, ensure_ascii=False).encode(
                    "utf-8"
                )
            )
            digest.update(b"\n")
            count += 1
        result[table.name] = {"count": count, "sha256": digest.hexdigest()}
    return result


if __name__ == "__main__":
    with engine.connect() as connection:
        print(json.dumps(fingerprints(connection), sort_keys=True))
