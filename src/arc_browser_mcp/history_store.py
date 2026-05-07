from __future__ import annotations

import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from arc_browser_mcp.models import ArcHistoryRecord, SourceInfo
from arc_browser_mcp.url_utils import chrome_time_to_datetime, extract_domain, normalize_text


class ArcHistoryStore:
    def __init__(self, user_data_dir: Path | None = None) -> None:
        default_user_data_dir = Path.home() / "Library/Application Support/Arc/User Data"
        self.user_data_dir = user_data_dir or default_user_data_dir

    def search(
        self,
        query: str | None = None,
        domain: str | None = None,
        profile_id: str | None = None,
        include_hidden: bool = False,
        limit: int = 50,
    ) -> list[ArcHistoryRecord]:
        rows: list[ArcHistoryRecord] = []
        normalized_domain = domain.lower() if domain else None
        normalized_query = normalize_text(query)

        with tempfile.TemporaryDirectory() as tempdir:
            snapshot_dir = Path(tempdir)
            for history_path in self.user_data_dir.glob("*/History"):
                profile_dir = history_path.parent.name
                if profile_id and profile_id != profile_dir:
                    continue
                copied_history = self._copy_history(history_path, snapshot_dir / profile_dir)
                rows.extend(
                    self._read_profile(
                        copied_history,
                        profile_dir=profile_dir,
                        query=normalized_query,
                        domain=normalized_domain,
                        include_hidden=include_hidden,
                    )
                )

        rows.sort(
            key=lambda row: row.last_visit_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        return rows[:limit]

    def _copy_history(self, path: Path, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{path}{suffix}")
            if sidecar.exists():
                shutil.copy2(sidecar, Path(f"{destination}{suffix}"))
        return destination

    def _read_profile(
        self,
        path: Path,
        *,
        profile_dir: str,
        query: str,
        domain: str | None,
        include_hidden: bool,
    ) -> list[ArcHistoryRecord]:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """
                SELECT id, url, title, visit_count, typed_count, last_visit_time, hidden
                FROM urls
                """
            )
            return [
                self._record_from_row(row, profile_dir=profile_dir, path=path)
                for row in rows
                if self._matches_row(
                    row,
                    query=query,
                    domain=domain,
                    include_hidden=include_hidden,
                )
            ]
        finally:
            connection.close()

    def _matches_row(
        self,
        row: sqlite3.Row,
        *,
        query: str,
        domain: str | None,
        include_hidden: bool,
    ) -> bool:
        row_domain = extract_domain(row["url"])
        if row["hidden"] and not include_hidden:
            return False
        if domain and row_domain != domain:
            return False
        if query:
            searchable = normalize_text(f"{row['title']} {row['url']} {row_domain or ''}")
            return query in searchable
        return True

    def _record_from_row(
        self,
        row: sqlite3.Row,
        *,
        profile_dir: str,
        path: Path,
    ) -> ArcHistoryRecord:
        return ArcHistoryRecord(
            id=f"{profile_dir}:{row['id']}",
            url=row["url"],
            title=row["title"] or "",
            domain=extract_domain(row["url"]),
            profile_id=profile_dir,
            profile_dir=profile_dir,
            last_visit_at=chrome_time_to_datetime(row["last_visit_time"]),
            visit_count=row["visit_count"],
            typed_count=row["typed_count"],
            hidden=bool(row["hidden"]),
            sources=[
                SourceInfo(
                    kind="history",
                    name=f"History/{profile_dir}",
                    path=str(path),
                )
            ],
        )
