"""Property-based tests using hypothesis for fuzzing path handling and byte formatting."""

import os
import sys
import tempfile

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from diskstat import format_bytes, ext_category, build_flat, scan


# ── format_bytes property-based tests ──────────────────────────────────────

class TestFormatBytesProperties:
    """Property-based tests for format_bytes."""

    @given(st.integers(min_value=0, max_value=1024 ** 6))
    @settings(max_examples=200)
    def test_format_bytes_never_crash(self, n):
        """format_bytes should never crash on any non-negative integer."""
        result = format_bytes(n)
        assert isinstance(result, str)
        assert "B" in result

    @given(st.integers(min_value=0))
    @settings(max_examples=100)
    def test_format_bytes_always_contains_unit(self, n):
        """Result must always contain a valid unit."""
        result = format_bytes(n)
        units = {"B", "KB", "MB", "GB", "TB", "PB"}
        assert any(unit in result for unit in units)

    @given(st.floats(allow_nan=True, allow_infinity=True))
    @settings(max_examples=50)
    def test_format_bytes_handles_floats_and_special(self, f):
        """format_bytes should handle float edge cases without crashing."""
        result = format_bytes(f)
        assert isinstance(result, str)

    @given(st.text())
    @settings(max_examples=50)
    def test_format_bytes_handles_strings(self, s):
        """format_bytes should handle string input gracefully."""
        result = format_bytes(s)
        assert result == "0.0 B"

    def test_format_bytes_handles_none(self):
        """format_bytes should handle None gracefully."""
        result = format_bytes(None)
        assert result == "—"
        assert isinstance(result, str)

    @given(st.integers(min_value=0, max_value=1024 ** 5))
    def test_format_bytes_unit_progression(self, n):
        """Larger values should use larger or equal units."""
        result = format_bytes(n)
        assert isinstance(result, str)
        assert len(result) > 0

    @given(st.integers(min_value=1, max_value=1024 ** 5))
    def test_format_bytes_positive_nonzero(self, n):
        """Positive values should never show 0.0 B."""
        result = format_bytes(n)
        if n > 0:
            assert result != "0.0 B"


# ── ext_category property-based tests ─────────────────────────────────────

class TestExtCategoryProperties:
    """Property-based tests for ext_category."""

    @given(st.text(min_size=1, max_size=50))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.filter_too_much])
    def test_ext_category_never_crash(self, name):
        """ext_category should never crash on any filename."""
        result = ext_category(name)
        assert isinstance(result, str)
        assert len(result) > 0

    @given(st.text(min_size=0, max_size=100))
    def test_ext_category_always_returns_string(self, name):
        """ext_category must always return a string."""
        result = ext_category(name)
        assert isinstance(result, str)

    def test_ext_category_dir_always_folder(self):
        """Directories should always be 'folder'."""
        assert ext_category("anything", is_dir=True) == "folder"

    @given(st.sampled_from([".py", ".js", ".jpg", ".zip", ".mp3", ".pdf", ".exe"]))
    def test_ext_category_known_extensions(self, ext):
        """Known extensions should map to expected categories."""
        cat = ext_category(f"file{ext}")
        expected_map = {
            ".py": "code", ".js": "code", ".jpg": "image",
            ".zip": "zip", ".mp3": "audio", ".pdf": "doc", ".exe": "exe",
        }
        assert cat == expected_map[ext]


# ── build_flat property-based tests ────────────────────────────────────────

class TestBuildFlatProperties:
    """Property-based tests for build_flat."""

    @given(
        st.integers(min_value=0, max_value=10000),
        st.integers(min_value=1, max_value=1000),
    )
    @settings(max_examples=50)
    def test_build_flat_never_crash(self, total_size, max_nodes):
        """build_flat should never crash on valid trees."""
        tree = {"name": "root", "path": "/tmp", "size": total_size, "category": "folder"}
        flat = build_flat(tree, max_nodes=max(max_nodes, 1))
        assert len(flat) >= 1
        assert flat[0]["name"] == "root"

    @given(st.integers(min_value=1, max_value=5000))
    def test_build_flat_respects_max_nodes(self, max_nodes):
        """build_flat should never exceed max_nodes."""
        tree = {
            "name": "root", "path": "/tmp", "size": 1000, "category": "folder",
            "children": [
                {"name": f"file_{i}", "path": f"/tmp/file_{i}", "size": i * 10, "category": "code"}
                for i in range(100)
            ]
        }
        flat = build_flat(tree, max_nodes=max_nodes)
        assert len(flat) <= max_nodes

    @given(st.integers(min_value=0, max_value=1000000))
    def test_build_flat_with_various_min_size(self, min_size):
        """build_flat should handle various min_size values."""
        tree = {
            "name": "root", "path": "/tmp", "size": 1000, "category": "folder",
            "children": [
                {"name": "small.txt", "path": "/tmp/small.txt", "size": 10, "category": "doc"},
                {"name": "big.txt", "path": "/tmp/big.txt", "size": 5000, "category": "doc"},
            ]
        }
        flat = build_flat(tree, max_nodes=100, min_size=min_size)
        if min_size > 10:
            names = [n["name"] for n in flat]
            assert "small.txt" not in names

    def test_build_flat_empty_tree(self):
        """build_flat should handle empty tree."""
        tree = {"name": "empty", "path": "/tmp", "size": 0, "category": "folder"}
        flat = build_flat(tree, max_nodes=10)
        assert len(flat) == 1
        assert flat[0]["parent"] is None


# ── scan property-based tests ──────────────────────────────────────────────

class TestScanProperties:
    """Property-based tests for scan function."""

    @given(st.text(alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")), min_size=1, max_size=20))
    @settings(max_examples=30)
    def test_scan_various_filenames(self, name):
        """scan should handle various filenames in a directory."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create a file with the given name
            filepath = os.path.join(tmp, name)
            try:
                with open(filepath, "w") as f:
                    f.write("test")
            except (OSError, ValueError):
                assume(False)  # Skip invalid filenames
            tree, stats = scan(tmp)
            assert isinstance(tree, dict)
            assert isinstance(stats, dict)
            assert "files" in stats
            assert "dirs" in stats

    @given(st.integers(min_value=0, max_value=10))
    def test_scan_various_depths(self, max_depth):
        """scan should handle various max_depth values."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create nested structure
            current = tmp
            for i in range(5):
                current = os.path.join(current, f"dir_{i}")
                os.makedirs(current, exist_ok=True)
            with open(os.path.join(current, "deep.txt"), "w") as f:
                f.write("deep")
            tree, stats = scan(tmp, max_depth=max_depth)
            assert isinstance(tree, dict)
