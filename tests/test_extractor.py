from __future__ import annotations

from datetime import datetime, timezone

from psnself.sync.extractor import _ensure_utc, _parse_date_utc, _normalize_name


class TestEnsureUtc:
    def test_naive_datetime(self) -> None:
        dt = datetime(2024, 12, 25, 10, 0, 0)
        result = _ensure_utc(dt)
        assert result.tzinfo is timezone.utc
        assert result.hour == 10

    def test_aware_datetime(self) -> None:
        dt = datetime(2024, 12, 25, 10, 0, 0, tzinfo=timezone.utc)
        result = _ensure_utc(dt)
        assert result is dt


class TestParseDateUtc:
    def test_iso_with_z(self) -> None:
        dt = _parse_date_utc("2024-12-25T10:00:00Z")
        assert dt.year == 2024
        assert dt.month == 12
        assert dt.day == 25
        assert dt.tzinfo is not None

    def test_iso_with_offset(self) -> None:
        dt = _parse_date_utc("2024-12-25T10:00:00+00:00")
        assert dt.tzinfo is not None

    def test_naive_iso(self) -> None:
        dt = _parse_date_utc("2024-12-25T10:00:00")
        assert dt.tzinfo is timezone.utc


class TestNormalizeName:
    def test_lowercase_and_strip(self) -> None:
        assert _normalize_name("  HELLO WORLD  ") == "hello world"

    def test_remove_trademark(self) -> None:
        assert _normalize_name("God of War™") == "god of war"

    def test_remove_registered(self) -> None:
        assert _normalize_name("Test® Game") == "test game"

    def test_remove_newlines(self) -> None:
        assert _normalize_name("Line1\nLine2") == "line1line2"

    def test_normalize_quotes(self) -> None:
        assert _normalize_name("\u2018hello\u2019") == "'hello'"

    def test_suffix_trophies(self) -> None:
        assert _normalize_name("Game Name Trophies") == "game name"

    def test_collapse_whitespace(self) -> None:
        assert _normalize_name("a    b") == "a b"
