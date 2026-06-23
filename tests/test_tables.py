import pytest

from file_organizer.display.tables import (
    _health_score,
    _score_color,
    _score_label,
    fmt_bytes,
)
from file_organizer.services.duplicates import SpaceSummary


def _summary(total=0, reclaimable=0, junk=0, dup_wasted=0, total_files=0):
    return SpaceSummary(
        total_files=total_files,
        total_size_bytes=total,
        duplicate_wasted_bytes=dup_wasted,
        junk_bytes=junk,
        reclaimable_bytes=reclaimable,
    )


# ── fmt_bytes ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("b,expected", [
    (0,              "0.0 B"),
    (1,              "1.0 B"),
    (1023,           "1023.0 B"),
    (1024,           "1.0 KB"),
    (1025,           "1.0 KB"),
    (1023 * 1024,    "1023.0 KB"),
    (1024 * 1024,    "1.0 MB"),
    (1024 ** 3,      "1.0 GB"),
    (1024 ** 4,      "1.0 TB"),
    (1024 ** 5,      "1.0 PB"),
])
def test_fmt_bytes_unit_boundaries(b, expected):
    assert fmt_bytes(b) == expected


# ── _health_score ─────────────────────────────────────────────────────────────

def test_health_score_zero_total_returns_100():
    assert _health_score(_summary(total=0, reclaimable=0)) == 100


def test_health_score_no_waste_returns_100():
    assert _health_score(_summary(total=1000, reclaimable=0)) == 100


def test_health_score_zero_waste_ratio():
    s = _summary(total=5000, reclaimable=0)
    assert _health_score(s) == 100


def test_health_score_50_percent_waste():
    s = _summary(total=1000, reclaimable=500)
    score = _health_score(s)
    assert score == 40


def test_health_score_10_percent_waste():
    s = _summary(total=1000, reclaimable=100)
    score = _health_score(s)
    assert score == int(100 - 0.1 * 120)


def test_health_score_100_percent_waste_clamped_to_zero():
    s = _summary(total=100, reclaimable=100)
    assert _health_score(s) == 0


def test_health_score_over_100_percent_waste_clamped():
    s = _summary(total=100, reclaimable=200)
    assert _health_score(s) == 0


def test_health_score_always_in_range():
    for reclaimable in range(0, 1100, 100):
        s = _summary(total=1000, reclaimable=reclaimable)
        score = _health_score(s)
        assert 0 <= score <= 100


def test_health_score_junk_contributes_to_reclaimable():
    s = _summary(total=1000, reclaimable=500, junk=500, dup_wasted=0)
    assert _health_score(s) == 40


# ── _score_color ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("score,color", [
    (100, "green"),
    (80,  "green"),
    (79,  "yellow"),
    (50,  "yellow"),
    (49,  "red"),
    (0,   "red"),
])
def test_score_color_thresholds(score, color):
    assert _score_color(score) == color


# ── _score_label ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("score,label", [
    (100, "CLEAN"),
    (80,  "CLEAN"),
    (79,  "GOOD"),
    (60,  "GOOD"),
    (59,  "NEEDS ATTENTION"),
    (40,  "NEEDS ATTENTION"),
    (39,  "CRITICAL"),
    (0,   "CRITICAL"),
])
def test_score_label_thresholds(score, label):
    assert _score_label(score) == label
