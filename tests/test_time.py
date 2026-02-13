"""时间格式转换工具测试。"""
import pytest
from utils.time import time_to_seconds, seconds_to_time


def test_time_to_seconds_basic():
    assert time_to_seconds("00:00:00.000") == 0.0
    assert time_to_seconds("00:00:01.500") == 1.5
    assert time_to_seconds("00:01:00.000") == 60.0
    assert time_to_seconds("01:00:00.000") == 3600.0
    assert time_to_seconds("01:02:03.250") == 3600 + 120 + 3.25


def test_time_to_seconds_no_ms():
    assert time_to_seconds("00:00:05") == 5.0


def test_time_to_seconds_invalid():
    with pytest.raises(ValueError, match="无效的时间格式"):
        time_to_seconds("invalid")
    with pytest.raises(ValueError):
        time_to_seconds("00:00")  # 缺少秒


def test_seconds_to_time_basic():
    assert seconds_to_time(0) == "00:00:00.000"
    assert seconds_to_time(1.5) == "00:00:01.500"
    assert seconds_to_time(65.5) == "00:01:05.500"
    assert seconds_to_time(3661.123) == "01:01:01.123"


def test_roundtrip():
    for sec in (0, 1.5, 65.25, 3600.5):
        assert time_to_seconds(seconds_to_time(sec)) == pytest.approx(sec)
