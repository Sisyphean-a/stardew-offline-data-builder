from __future__ import annotations

import sqlite3


def sqlite_supports_fts4() -> bool:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE VIRTUAL TABLE test_fts USING fts4(content)")
    except sqlite3.DatabaseError:
        return False
    finally:
        connection.close()
    return True
