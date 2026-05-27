from datetime import datetime, timedelta

from utils import format_age


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def test_just_now():
    assert format_age(_ts(datetime.now() - timedelta(seconds=30))) == "just now"


def test_minutes_ago():
    assert format_age(_ts(datetime.now() - timedelta(minutes=5))) == "5m ago"


def test_59_minutes_ago():
    assert format_age(_ts(datetime.now() - timedelta(minutes=59))) == "59m ago"


def test_today_shows_time_not_relative():
    dt = datetime.now() - timedelta(hours=2)
    result = format_age(_ts(dt))
    assert "ago" not in result
    assert ":" in result  # time format like "2:30 PM"


def test_yesterday():
    dt = datetime.now() - timedelta(days=1)
    assert format_age(_ts(dt)).startswith("yesterday")


def test_older_shows_short_date():
    dt = datetime.now() - timedelta(days=10)
    result = format_age(_ts(dt))
    assert "ago" not in result
    assert "yesterday" not in result
    assert len(result) > 0


def test_invalid_timestamp():
    assert format_age("not-a-date") == ""


def test_none_timestamp():
    assert format_age(None) == ""
