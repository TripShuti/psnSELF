from __future__ import annotations

from types import SimpleNamespace

from psnself import db
from psnself.models import Trophy
from psnself.sync.extractor import _extract_group_data
from psnself.sync.trophy_sync import _defined_trophy_total, _stored_trophy_count


def _title(bronze: int, silver: int, gold: int, platinum: int):
    return SimpleNamespace(
        defined_trophies=SimpleNamespace(
            bronze=bronze, silver=silver, gold=gold, platinum=platinum
        )
    )


class TestDefinedTrophyTotal:
    def test_sums_all_types(self) -> None:
        assert _defined_trophy_total(_title(99, 24, 13, 1)) == 137

    def test_broken_title_returns_none(self) -> None:
        assert _defined_trophy_total(SimpleNamespace()) is None
        assert _defined_trophy_total(SimpleNamespace(defined_trophies=None)) is None


class TestStoredTrophyCount:
    def test_counts_rows(self, conn) -> None:
        conn.execute(
            "INSERT INTO games (np_communication_id, title_name)"
            " VALUES ('NP1', 'G')"
        )
        assert _stored_trophy_count(conn, "NP1") == 0
        conn.execute(
            "INSERT INTO trophies (np_communication_id, trophy_id)"
            " VALUES ('NP1', 1), ('NP1', 2)"
        )
        assert _stored_trophy_count(conn, "NP1") == 2


class TestExtractGroupData:
    def test_values(self) -> None:
        g = SimpleNamespace(trophy_group_id="001", trophy_group_name="Series II")
        assert _extract_group_data("NP1", g) == {
            "np_communication_id": "NP1",
            "trophy_group_id": "001",
            "trophy_group_name": "Series II",
        }

    def test_missing_id_defaults(self) -> None:
        assert _extract_group_data("NP1", SimpleNamespace()) == {
            "np_communication_id": "NP1",
            "trophy_group_id": "default",
            "trophy_group_name": None,
        }


class TestTrophyGroupRoundtrip:
    def test_get_trophies_includes_group_name(self, conn) -> None:
        conn.execute(
            "INSERT INTO games (np_communication_id, title_name)"
            " VALUES ('NP1', 'G')"
        )
        conn.execute(
            "INSERT INTO trophies (np_communication_id, trophy_id,"
            " trophy_name, trophy_group_id)"
            " VALUES ('NP1', 5, 'T', '001')"
        )
        db.upsert_trophy_group(conn, {
            "np_communication_id": "NP1",
            "trophy_group_id": "001",
            "trophy_group_name": "Series II",
        })
        rows = db.get_trophies(conn, "NP1")
        assert len(rows) == 1
        t = Trophy.from_row(rows[0])
        assert t.trophy_group_id == "001"
        assert t.trophy_group_name == "Series II"

    def test_missing_group_row_falls_back_to_id(self, conn) -> None:
        conn.execute(
            "INSERT INTO games (np_communication_id, title_name)"
            " VALUES ('NP1', 'G')"
        )
        conn.execute(
            "INSERT INTO trophies (np_communication_id, trophy_id,"
            " trophy_name, trophy_group_id)"
            " VALUES ('NP1', 5, 'T', 'default')"
        )
        t = Trophy.from_row(db.get_trophies(conn, "NP1")[0])
        assert t.trophy_group_id == "default"
        assert t.trophy_group_name is None
