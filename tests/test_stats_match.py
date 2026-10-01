from __future__ import annotations

import sqlite3
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

from psnself.sync.trophy_sync import _find_ts_stats


def _title(name: str, np_title_id: str | None = None) -> Any:
    return SimpleNamespace(title_name=name, np_title_id=np_title_id)


def _stats(title_id: str, name: str) -> Any:
    return SimpleNamespace(
        title_id=title_id,
        name=name,
        play_duration=timedelta(seconds=100),
        play_count=1,
        first_played_date_time=None,
        last_played_date_time=None,
    )


def _seed(conn: sqlite3.Connection, np_comm_id: str,
          games_tid: str | None, gs_tid: str | None) -> None:
    conn.execute(
        "INSERT INTO games (np_communication_id, np_title_id, title_name)"
        " VALUES (?, ?, 'Genshin Impact')",
        (np_comm_id, games_tid),
    )
    conn.execute(
        "INSERT INTO game_stats (np_communication_id, title_id, total_seconds)"
        " VALUES (?, ?, 0)",
        (np_comm_id, gs_tid),
    )


class TestFindTsStats:
    def test_stored_title_id_used_when_api_id_missing(self, conn) -> None:
        _seed(conn, "NPWR22724_00", "PPSA02584_00", "PPSA02584_00")
        psn = _stats("PPSA02584_00", "Genshin Impact 6th Anniversary")
        got = _find_ts_stats(
            conn, _title("Genshin Impact", None), "NPWR22724_00",
            {"PPSA02584_00": psn}, {"genshin impact 6th anniversary": psn},
        )
        assert got is psn

    def test_exact_name_preferred_over_prefix_candidate(self, conn) -> None:
        exact = _stats("PPSA1", "Kingdom Come: Deliverance")
        other = _stats("PPSA2", "Kingdom Come: Deliverance II")
        got = _find_ts_stats(
            conn, _title("Kingdom Come: Deliverance", "UNKNOWN"), "NP1",
            {"PPSA1": exact, "PPSA2": other},
            {"kingdom come: deliverance": exact,
             "kingdom come: deliverance ii": other},
        )
        assert got is exact

    def test_unambiguous_rename_suffix_matches(self, conn) -> None:
        psn = _stats("PPSA02584_00", "Genshin Impact 6th Anniversary")
        got = _find_ts_stats(
            conn, _title("Genshin Impact", "UNKNOWN"), "NP_NEW",
            {"PPSA02584_00": psn}, {"genshin impact 6th anniversary": psn},
        )
        assert got is psn

    def test_ambiguous_prefix_returns_none(self, conn) -> None:
        first = _stats("PPSA1", "Kingdom Come: Deliverance Special")
        second = _stats("PPSA2", "Kingdom Come: Deliverance II Plus")
        got = _find_ts_stats(
            conn, _title("Kingdom Come: Deliverance", "UNKNOWN"), "NP_NEW",
            {"PPSA1": first, "PPSA2": second},
            {"kingdom come: deliverance special": first,
             "kingdom come: deliverance ii plus": second},
        )
        assert got is None

    def test_no_match_returns_none(self, conn) -> None:
        got = _find_ts_stats(
            conn, _title("Some Game", "UNKNOWN"), "NP_NEW",
            {}, {},
        )
        assert got is None
