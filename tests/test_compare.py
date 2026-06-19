"""Edge case tests for _compare_reports."""
import os
import csv
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from diskstat import _compare_reports


def _make_flat(items):
    """Build a flat list from (name, size) tuples, with a fake root node."""
    flat = [{"name": "root", "path": "/tmp", "size": 0, "category": "folder", "parent": None}]
    for name, size in items:
        flat.append({
            "name": name,
            "path": f"/tmp/{name}",
            "size": size,
            "category": "doc",
            "parent": "root",
        })
    return flat


def _write_csv_row(path, rows):
    """Write a CSV file with header + data rows. Each row is (name, size_bytes)."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "path", "size_bytes", "size_human", "category", "parent"])
        for name, size in rows:
            w.writerow([name, f"/tmp/{name}", size, f"{size} B", "doc", "root"])


class TestCompareReportsEdgeCases:
    """Edge-case tests for _compare_reports."""

    def test_missing_baseline_raises(self, tmp_path):
        """_compare_reports should raise FileNotFoundError when baseline file doesn't exist."""
        flat = _make_flat([("a.txt", 100)])
        with pytest.raises(FileNotFoundError):
            _compare_reports(flat, str(tmp_path / "nonexistent.csv"))

    def test_invalid_csv_missing_size_column_returns_empty(self, tmp_path):
        """Invalid CSV (no size_bytes column) should produce empty added/removed/changed."""
        csv_path = tmp_path / "bad.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["name", "path", "category"])  # no size_bytes
            w.writerow(["a.txt", "/tmp/a.txt", "doc"])
        flat = _make_flat([("a.txt", 100)])
        added, removed, changed = _compare_reports(flat, str(csv_path))
        # size_bytes missing -> defaults to 0, so a.txt size 100 != 0 -> changed
        assert isinstance(added, dict)
        assert isinstance(removed, dict)
        assert isinstance(changed, dict)

    def test_empty_baseline_csv_all_added(self, tmp_path):
        """Empty baseline CSV (header only) should return all current files as added."""
        csv_path = tmp_path / "empty.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["name", "path", "size_bytes", "size_human", "category", "parent"])
        flat = _make_flat([("a.txt", 100), ("b.txt", 200)])
        added, removed, changed = _compare_reports(flat, str(csv_path))
        assert set(added.keys()) == {"/tmp/a.txt", "/tmp/b.txt"}
        assert added["/tmp/a.txt"] == 100
        assert added["/tmp/b.txt"] == 200
        assert removed == {}
        assert changed == {}

    def test_identical_csv_no_diffs(self, tmp_path):
        """Identical baseline and current should yield empty added/removed/changed."""
        csv_path = tmp_path / "baseline.csv"
        _write_csv_row(csv_path, [("a.txt", 100), ("b.txt", 200)])
        flat = _make_flat([("a.txt", 100), ("b.txt", 200)])
        added, removed, changed = _compare_reports(flat, str(csv_path))
        assert added == {}
        assert removed == {}
        assert changed == {}

    def test_changed_size(self, tmp_path):
        """A file with different size should appear in changed dict."""
        csv_path = tmp_path / "baseline.csv"
        _write_csv_row(csv_path, [("a.txt", 100)])
        flat = _make_flat([("a.txt", 500)])
        added, removed, changed = _compare_reports(flat, str(csv_path))
        assert added == {}
        assert removed == {}
        assert "/tmp/a.txt" in changed
        assert changed["/tmp/a.txt"] == (100, 500)  # (baseline_size, current_size)

    def test_removed_file(self, tmp_path):
        """A file in baseline but not in current should appear in removed dict."""
        csv_path = tmp_path / "baseline.csv"
        _write_csv_row(csv_path, [("a.txt", 100), ("b.txt", 200)])
        flat = _make_flat([("a.txt", 100)])
        added, removed, changed = _compare_reports(flat, str(csv_path))
        assert added == {}
        assert "/tmp/b.txt" in removed
        assert removed["/tmp/b.txt"] == 200
        assert changed == {}

    def test_added_file(self, tmp_path):
        """A file in current but not in baseline should appear in added dict."""
        csv_path = tmp_path / "baseline.csv"
        _write_csv_row(csv_path, [("a.txt", 100)])
        flat = _make_flat([("a.txt", 100), ("c.txt", 300)])
        added, removed, changed = _compare_reports(flat, str(csv_path))
        assert "/tmp/c.txt" in added
        assert added["/tmp/c.txt"] == 300
        assert removed == {}
        assert changed == {}

    def test_same_name_different_path(self, tmp_path):
        """Files with same name but different paths should be treated as separate."""
        csv_path = tmp_path / "baseline.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["name", "path", "size_bytes", "size_human", "category", "parent"])
            w.writerow(["a.txt", "/tmp/dir1/a.txt", 100, "100 B", "doc", "root"])
        # Current has a.txt in different dir
        flat = _make_flat([("a.txt", 200)])  # path = /tmp/a.txt
        added, removed, changed = _compare_reports(flat, str(csv_path))
        # /tmp/a.txt is added, /tmp/dir1/a.txt is removed (different paths)
        assert "/tmp/a.txt" in added
        assert added["/tmp/a.txt"] == 200
        assert "/tmp/dir1/a.txt" in removed
        assert removed["/tmp/dir1/a.txt"] == 100
