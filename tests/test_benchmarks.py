"""Benchmark tests for performance regression detection."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from diskstat import format_bytes, ext_category, build_flat, scan


class TestBenchmarkFormatBytes:
    """Benchmark format_bytes performance."""

    def test_benchmark_format_bytes_small(self, benchmark):
        """Benchmark format_bytes with small values."""
        result = benchmark(format_bytes, 500)
        assert result == "500.0 B"

    def test_benchmark_format_bytes_large(self, benchmark):
        """Benchmark format_bytes with large values."""
        result = benchmark(format_bytes, 1024 ** 4)
        assert "TB" in result

    def test_benchmark_format_bytes_edge(self, benchmark):
        """Benchmark format_bytes with edge cases."""
        result = benchmark(format_bytes, 0)
        assert result == "0.0 B"


class TestBenchmarkExtCategory:
    """Benchmark ext_category performance."""

    def test_benchmark_ext_category_known(self, benchmark):
        """Benchmark ext_category with known extension."""
        result = benchmark(ext_category, "test.py")
        assert result == "code"

    def test_benchmark_ext_category_unknown(self, benchmark):
        """Benchmark ext_category with unknown extension."""
        result = benchmark(ext_category, "file.xyz")
        assert result == "unknown"

    def test_benchmark_ext_category_dir(self, benchmark):
        """Benchmark ext_category for directories."""
        result = benchmark(ext_category, "folder", is_dir=True)
        assert result == "folder"


class TestBenchmarkBuildFlat:
    """Benchmark build_flat performance."""

    @pytest.fixture
    def large_tree(self):
        """Create a tree with many children for benchmarking."""
        children = [
            {"name": f"file_{i}.txt", "path": f"/tmp/file_{i}.txt", "size": i * 100, "category": "doc"}
            for i in range(1000)
        ]
        return {
            "name": "root",
            "path": "/tmp",
            "size": sum(c["size"] for c in children),
            "category": "folder",
            "children": children,
        }

    def test_benchmark_build_flat_small(self, benchmark):
        """Benchmark build_flat with small tree."""
        tree = {
            "name": "root", "path": "/tmp", "size": 100, "category": "folder",
            "children": [
                {"name": f"f{i}", "path": f"/tmp/f{i}", "size": i * 10, "category": "code"}
                for i in range(10)
            ]
        }
        result = benchmark(build_flat, tree, max_nodes=100)
        assert len(result) > 0

    def test_benchmark_build_flat_large(self, benchmark, large_tree):
        """Benchmark build_flat with large tree."""
        result = benchmark(build_flat, large_tree, max_nodes=5000)
        assert len(result) > 0

    def test_benchmark_build_flat_with_filters(self, benchmark, large_tree):
        """Benchmark build_flat with category filter."""
        result = benchmark(build_flat, large_tree, max_nodes=5000, categories={"doc"})
        assert len(result) > 0


class TestBenchmarkScan:
    """Benchmark scan performance."""

    def test_benchmark_scan_small_dir(self, benchmark):
        """Benchmark scan on a small directory."""
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(10):
                with open(os.path.join(tmp, f"file_{i}.txt"), "w") as f:
                    f.write("x" * 100)
            tree, stats = benchmark(scan, tmp)
            assert tree["name"] == os.path.basename(tmp)
            assert stats["files"] == 10

    def test_benchmark_scan_medium_dir(self, benchmark):
        """Benchmark scan on a medium directory."""
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(100):
                with open(os.path.join(tmp, f"file_{i}.txt"), "w") as f:
                    f.write("x" * 100)
            tree, stats = benchmark(scan, tmp)
            assert stats["files"] == 100

    def test_benchmark_scan_nested(self, benchmark):
        """Benchmark scan on nested directory structure."""
        with tempfile.TemporaryDirectory() as tmp:
            current = tmp
            for i in range(5):
                current = os.path.join(current, f"dir_{i}")
                os.makedirs(current, exist_ok=True)
                for j in range(5):
                    with open(os.path.join(current, f"file_{j}.txt"), "w") as f:
                        f.write("x" * 50)
            tree, stats = benchmark(scan, tmp)
            assert stats["files"] == 25
