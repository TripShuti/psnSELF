from __future__ import annotations

from psnself.web.utils import fmt_date, fmt_hms, _parse_play_time


def test_fmt_date_none() -> None:
    assert fmt_date(None) == "–"
    assert fmt_date("") == "–"


def test_fmt_date() -> None:
    assert fmt_date("2024-12-25T10:00:00") == "25/12"


def test_fmt_hms_zero() -> None:
    assert fmt_hms(0) == "0m"
    assert fmt_hms(None) == "0m"


def test_fmt_hms_only_minutes() -> None:
    assert fmt_hms(30) == "0m"
    assert fmt_hms(300) == "5m"


def test_fmt_hms_hours_and_minutes() -> None:
    assert fmt_hms(3661) == "1h 1m"
    assert fmt_hms(7200) == "2h 0m"
    assert fmt_hms(7500) == "2h 5m"


def test_parse_play_time_hours() -> None:
    assert _parse_play_time("3h") == 3 * 3600


def test_parse_play_time_hours_decimal() -> None:
    assert _parse_play_time("2.5h") == 9000


def test_parse_play_time_hours_and_minutes() -> None:
    assert _parse_play_time("2h 30m") == 9000


def test_parse_play_time_decimal_hours_and_minutes() -> None:
    assert _parse_play_time("2.5h 30m") == 10800


def test_parse_play_time_minutes() -> None:
    assert _parse_play_time("45m") == 45 * 60


def test_parse_play_time_invalid() -> None:
    assert _parse_play_time("") is None
    assert _parse_play_time("abc") is None
