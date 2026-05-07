import sqlite3
from pathlib import Path

from arc_browser_mcp.history_store import ArcHistoryStore


def create_history_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE urls (
                id INTEGER PRIMARY KEY,
                url TEXT NOT NULL,
                title TEXT,
                visit_count INTEGER,
                typed_count INTEGER,
                last_visit_time INTEGER,
                hidden INTEGER
            )
            """
        )
        connection.execute(
            """
            INSERT INTO urls (
                id, url, title, visit_count, typed_count, last_visit_time, hidden
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "https://example.com/page",
                "Example Page",
                5,
                1,
                13217451500000000,
                0,
            ),
        )
        connection.execute(
            """
            INSERT INTO urls (
                id, url, title, visit_count, typed_count, last_visit_time, hidden
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                2,
                "https://hidden.example.com",
                "Hidden Page",
                1,
                0,
                13217451500000001,
                1,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def test_search_snapshot_without_hidden_by_default(tmp_path: Path) -> None:
    create_history_db(tmp_path / "Profile 1" / "History")

    store = ArcHistoryStore(user_data_dir=tmp_path)
    rows = store.search(query="Example", limit=10)

    assert len(rows) == 1
    assert rows[0].url == "https://example.com/page"
    assert rows[0].domain == "example.com"
    assert rows[0].profile_dir == "Profile 1"
    assert rows[0].visit_count == 5


def test_search_snapshot_can_include_hidden_rows(tmp_path: Path) -> None:
    create_history_db(tmp_path / "Profile 1" / "History")

    store = ArcHistoryStore(user_data_dir=tmp_path)
    rows = store.search(domain="hidden.example.com", include_hidden=True, limit=10)

    assert [row.title for row in rows] == ["Hidden Page"]
