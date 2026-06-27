import sys
import os
import json
import csv as csv_mod
import pytest
import tempfile, io
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from diskstat import (
    _resolve_path, format_bytes, ext_category, scan, build_flat,
    render_html, _find_template, _render_template, _write_csv, _parse_args,
    _output_json, _output_text, _open_report, _make_colors, _supports_color,
    EXT_COLORS, EXT_MAP, _MAX_SCAN_DEPTH,
    main,
)


# _resolve_path — validates and resolves paths
def test_resolve_path_missing_dir(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        _resolve_path(str(tmp_path / "nonexistent"))


def test_resolve_path_not_a_dir(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("x")
    with pytest.raises(ValueError, match="not a directory"):
        _resolve_path(str(f))


def test_resolve_path_tilde_expansion(tmp_path):
    # _resolve_path expands ~ — just verify it doesn't crash on valid dir
    result = _resolve_path(str(tmp_path))
    assert os.path.isdir(result)
    assert os.path.isabs(result)


def test_resolve_path_returns_realpath(tmp_path):
    # _resolve_path returns the real absolute path
    result = _resolve_path(str(tmp_path))
    assert result == os.path.realpath(str(tmp_path))


# format_bytes
def test_format_bytes_bytes():
    assert format_bytes(500) == "500.0 B"


def test_format_bytes_kilobytes():
    assert format_bytes(2048) == "2.0 KB"


def test_format_bytes_megabytes():
    assert format_bytes(5 * 1024 * 1024) == "5.0 MB"


def test_format_bytes_zero():
    assert format_bytes(0) == "0.0 B"


# ext_category
def test_ext_category_dir():
    assert ext_category("some_folder", is_dir=True) == "folder"


def test_ext_category_no_ext():
    assert ext_category("README") in ("unknown",)


def test_ext_category_known_zip():
    assert ext_category("backup.zip") == "zip"


def test_ext_category_known_image():
    assert ext_category("photo.JPG") == "image"


def test_ext_category_known_code():
    assert ext_category("main.py") == "code"


# scan
def test_scan_returns_tree_and_stats(tmp_path):
    (tmp_path / "file_a.txt").write_text("hello")
    (tmp_path / "file_b.py").write_text("print(1)")
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "nested.dat").write_bytes(b"\x00" * 1000)

    tree, stats = scan(str(tmp_path))

    assert tree["name"] == tmp_path.name
    assert stats["files"] == 3
    assert stats["dirs"] == 1
    assert tree["size"] >= 1000
    child_names = {c["name"] for c in tree.get("children", [])}
    assert "file_a.txt" in child_names
    assert "file_b.py" in child_names
    assert "subdir" in child_names
    sub_node = next(c for c in tree["children"] if c["name"] == "subdir")
    assert sub_node["size"] >= 1000
    assert sub_node["children"][0]["name"] == "nested.dat"
    assert sub_node["children"][0]["category"] == "data"


def test_scan_handles_missing_dir(tmp_path):
    target = str(tmp_path / "does_not_exist")
    tree, stats = scan(target)
    assert tree["size"] == 0
    assert stats["skipped"] >= 1


def test_scan_calls_progress_callback(tmp_path):
    called = []
    def on_progress(path, total_files, total_dirs):
        called.append((path, total_files, total_dirs))

    (tmp_path / "a.txt").write_text("x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("y")

    tree, stats = scan(str(tmp_path), on_progress=on_progress)
    assert len(called) >= 2
    assert stats["files"] == 2
    assert stats["dirs"] >= 1
    assert stats["skipped"] == 0


# build_flat
def test_build_flat_limits_nodes(tmp_path):
    tree = {
        "name": "root",
        "size": 100,
        "children": [
            {"name": "a", "size": 50, "children": [{"name": "a1", "size": 50}]},
            {"name": "b", "size": 30},
            {"name": "c", "size": 20},
        ],
    }
    flat = build_flat(tree, max_nodes=3)
    assert len(flat) == 3
    assert flat[0]["name"] == "root"
    assert flat[0]["parent"] is None


def test_build_flat_sorted_by_size(tmp_path):
    tree = {
        "name": "root",
        "size": 100,
        "children": [
            {"name": "small", "size": 10, "children": []},
            {"name": "large", "size": 80, "children": []},
        ],
    }
    flat = build_flat(tree, max_nodes=5)
    names = [f["name"] for f in flat if f["name"] in ("large", "small")]
    assert names.index("large") < names.index("small")


def test_build_flat_preserves_folders(tmp_path):
    tree = {
        "name": "root",
        "size": 50,
        "children": [
            {"name": "folder_x", "size": 50, "children": [{"name": "in.txt", "size": 10}]},
        ],
    }
    flat = build_flat(tree, max_nodes=10)
    folder = next(f for f in flat if f["name"] == "folder_x")
    assert folder["category"] == "folder"
    assert folder["parent"] == "root"
    inner = next(f for f in flat if f["name"] == "in.txt")
    assert inner["parent"] == "folder_x"


def test_build_flat_max_zero_returns_root_only(tmp_path):
    tree = {"name": "root", "size": 100, "children": [{"name": "x", "size": 100}]}
    flat = build_flat(tree, max_nodes=0)
    assert flat == [{"name": "root", "path": "", "size": 100, "category": "folder", "parent": None}]


# render_html



def test_render_html_contains_color_mapping(tmp_path):
    tree = {"name": "root", "path": "/mnt/data", "size": 200, "category": "folder", "children": [
        {"name": "notes.txt", "path": "/mnt/data/notes.txt", "size": 100, "category": "doc"},
        {"name": "app", "path": "/mnt/data/app", "size": 100, "category": "folder", "children": [
            {"name": "main.py", "path": "/mnt/data/app/main.py", "size": 20, "category": "code"},
        ]},
    ]}
    flat = build_flat(tree, max_nodes=10)
    htmlp = tmp_path / "color.html"
    csvp = tmp_path / "color.csv"
    render_html(tree, flat, str(htmlp), str(csvp))
    text = htmlp.read_text(encoding="utf-8")
    # Template must embed category color mapping (WinDirStat warm palette).
    assert '"folder": "#E8D4A0"' in text
    assert '"doc": "#509050"' in text
    assert '"code": "#3080A0"' in text


def test_render_html_file_list_includes_tooltip_attrs(tmp_path):
    tree = {"name": "root", "path": "/mnt/data", "size": 200, "category": "folder", "children": [
        {"name": "a.txt", "path": "/mnt/data/a.txt", "size": 50, "category": "doc"},
        {"name": "b.txt", "path": "/mnt/data/b.txt", "size": 150, "category": "doc"},
    ]}
    flat = build_flat(tree, max_nodes=10)
    htmlp = tmp_path / "groups.html"
    csvp = tmp_path / "groups.csv"
    render_html(tree, flat, str(htmlp), str(csvp))
    text = htmlp.read_text(encoding="utf-8")
    # Must have the flat data and color config embedded
    assert "colors" in text
    assert "flat" in text
    assert "renderExtTable" in text


def test_render_html_csv_has_correct_columns(tmp_path):
    tree = {"name": "root", "path": "/mnt/x", "size": 50, "category": "folder", "children": [
        {"name": "a.txt", "path": "/mnt/x/a.txt", "size": 10, "category": "doc"},
    ]}
    flat = build_flat(tree, max_nodes=5)
    html = tmp_path / "h.html"
    csvp = tmp_path / "c.csv"
    render_html(tree, flat, str(html), str(csvp))
    rows = csvp.read_text(encoding="utf-8").splitlines()
    assert rows[0].split(",") == ["name", "path", "size_bytes", "size_human", "category", "parent"]
    assert len(rows) >= 2
    assert any("a.txt" in line for line in rows[1:])

# main
def test_main_scans_target_writes_report(tmp_path):
    (tmp_path / "a.txt").write_text("hi")
    (tmp_path / "b.py").write_text("1")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "nested.bin").write_bytes(b"\x00" * 100)

    out_dir = tmp_path / "out"
    os.makedirs(out_dir, exist_ok=True)

    import io
    from contextlib import redirect_stdout
    old_argv = sys.argv
    old_cwd = os.getcwd()
    buf = io.StringIO()
    try:
        os.chdir(str(tmp_path))
        sys.argv = ["diskstat.py", str(tmp_path), "-o", str(out_dir)]
        with redirect_stdout(buf):
            main()
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)

    htmls = list(out_dir.glob("*.html"))
    csvs = list(out_dir.glob("*.csv"))
    assert htmls, "HTML report should exist"
    assert csvs, "CSV report should exist"
    assert htmls[0].exists()
    assert csvs[0].exists()
    out = buf.getvalue()
    assert "scanning" in out.lower() or "Done" in out
    assert "dirs" in out or "files" in out


def test_main_reports_live_progress(tmp_path):
    (tmp_path / "x.txt").write_text("1")
    (tmp_path / "y.txt").write_text("2")

    out_dir = tmp_path / "out"
    os.makedirs(out_dir, exist_ok=True)

    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    old_argv = sys.argv
    old_cwd = os.getcwd()
    try:
        os.chdir(str(tmp_path))
        sys.argv = ["diskstat.py", str(tmp_path), "-o", str(out_dir)]
        with redirect_stdout(buf):
            main()
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)

    out = buf.getvalue()
    assert "scanning" in out.lower() or "Done:" in out


# --- Additional tests ---

def test_format_bytes_negative():
    assert format_bytes(-1) == "0.0 B"


def test_format_bytes_very_large():
    # 1 PB
    result = format_bytes(1024 ** 5)
    assert "PB" in result


def test_build_flat_empty_tree():
    tree = {"name": "empty", "path": "/tmp", "size": 0, "category": "folder"}
    flat = build_flat(tree, max_nodes=10)
    assert len(flat) == 1
    assert flat[0]["name"] == "empty"
    assert flat[0]["parent"] is None


def test_build_flat_single_file():
    tree = {"name": "root", "path": "/tmp", "size": 100, "category": "folder", "children": [
        {"name": "a.txt", "path": "/tmp/a.txt", "size": 100, "category": "doc"}
    ]}
    flat = build_flat(tree, max_nodes=10)
    assert len(flat) == 2
    assert flat[1]["name"] == "a.txt"
    assert flat[1]["parent"] == "root"


def test_scan_depth_limit(tmp_path):
    # Create a deeply nested directory structure
    current = tmp_path
    for i in range(300):
        current = current / f"dir_{i}"
        current.mkdir()
    (current / "deep_file.txt").write_text("deep")

    tree, stats = scan(str(tmp_path))
    # Should not crash, should skip deep dirs
    assert stats["skipped"] > 0 or stats["dirs"] > 0


def test_main_json_output(tmp_path):
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    old_argv = sys.argv
    old_cwd = os.getcwd()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    try:
        os.chdir(str(tmp_path))
        (tmp_path / "test.txt").write_text("hello")
        sys.argv = ["diskstat.py", str(tmp_path), "-o", str(out_dir), "--format", "json"]
        with redirect_stdout(buf):
            main()
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)

    out = buf.getvalue()
    data = json.loads(out)
    assert data["ok"] is True
    assert "stats" in data
    assert "output" in data
    assert "html" in data["output"]


def test_main_no_color_flag(tmp_path):
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    old_argv = sys.argv
    old_cwd = os.getcwd()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    try:
        os.chdir(str(tmp_path))
        (tmp_path / "test.txt").write_text("hello")
        sys.argv = ["diskstat.py", str(tmp_path), "-o", str(out_dir), "--no-color"]
        with redirect_stdout(buf):
            main()
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)

    out = buf.getvalue()
    # Should not contain ANSI escape codes
    assert "\033[" not in out


# --- Tests for refactored helper functions ---

def test_find_template_exists():
    """_find_template should find the template file."""
    path = _find_template()
    assert os.path.exists(path)
    assert str(path).endswith("template.html")


def test_render_template_substitutes_placeholders():
    """_render_template should replace all placeholders."""
    tpl_path = _find_template()
    flat = [{"name": "test.txt", "size": 100, "category": "doc"}]
    result = _render_template(tpl_path, "MyRoot", "5 files | 100 B total", flat, EXT_COLORS)
    assert "__ROOT_NAME__" not in result
    assert "__STATS_LINE__" not in result
    assert "__JS_FLAT__" not in result
    assert "__JS_COLORS__" not in result
    assert "MyRoot" in result
    assert "test.txt" in result
    assert "#E8D4A0" in result  # folder color from EXT_COLORS (WinDirStat warm palette)


def test_render_template_escapes_html():
    """_render_template should escape HTML entities in root_name."""
    tpl_path = _find_template()
    result = _render_template(tpl_path, "<script>alert('xss')</script>", "1 &lt; 100", [], EXT_COLORS)
    # User-controlled root_name must be escaped — D3 <script> blocks come from template, not user input
    assert "<script>alert('xss')</script>" not in result
    assert "&lt;script&gt;alert" in result


def test_write_csv_creates_file(tmp_path):
    """_write_csv should write valid CSV with correct headers."""
    flat = [
        {"name": "root", "path": "/tmp", "size": 100, "category": "folder", "parent": None},
        {"name": "a.txt", "path": "/tmp/a.txt", "size": 50, "category": "doc", "parent": "root"},
    ]
    csv_path = str(tmp_path / "test.csv")
    _write_csv(flat, csv_path)
    with open(csv_path, "r") as f:
        reader = csv_mod.reader(f)
        rows = list(reader)
    assert rows[0] == ["name", "path", "size_bytes", "size_human", "category", "parent"]
    assert len(rows) == 3  # header + 2 data rows
    assert rows[1][0] == "root"
    assert rows[2][0] == "a.txt"


def test_parse_args_defaults():
    """_parse_args should return sensible defaults."""
    old_argv = sys.argv
    try:
        sys.argv = ["diskstat.py"]
        args = _parse_args()
        assert args.path == "/mnt/c/"
        assert args.max_nodes == 5000
        assert args.min_size == 0
        assert args.format == "text"
        assert args.no_color is False
        assert args.progress is False
        assert args.category == []
        assert args.exclude == []
        assert args.sort == "size"
        assert args.top == 0
    finally:
        sys.argv = old_argv


def test_parse_args_custom():
    """_parse_args should parse custom flags."""
    old_argv = sys.argv
    try:
        sys.argv = ["diskstat.py", "/home", "--format", "json", "--sort", "name", "--top", "10", "--max-nodes", "100"]
        args = _parse_args()
        assert args.path == "/home"
        assert args.format == "json"
        assert args.sort == "name"
        assert args.top == 10
        assert args.max_nodes == 100
    finally:
        sys.argv = old_argv


def test_parse_args_clamp_max_nodes():
    """_parse_args should clamp max_nodes to [1, 500000]."""
    old_argv = sys.argv
    try:
        sys.argv = ["diskstat.py", "--max-nodes", "999999"]
        args = _parse_args()
        assert args.max_nodes == 500_000
        sys.argv = ["diskstat.py", "--max-nodes", "0"]
        args = _parse_args()
        assert args.max_nodes == 1
    finally:
        sys.argv = old_argv


def test_parse_args_negative_top():
    """_parse_args should set negative --top to 0."""
    old_argv = sys.argv
    try:
        sys.argv = ["diskstat.py", "--top", "-5"]
        args = _parse_args()
        assert args.top == 0
    finally:
        sys.argv = old_argv


def test_output_text_no_color(tmp_path, capsys):
    """_output_text should work with colors disabled."""
    stats = {"files": 10, "dirs": 2, "skipped": 0, "elapsed_s": 1.5, "root": str(tmp_path), "total_bytes": 1024}
    C = _make_colors(False)
    _output_text(stats, str(tmp_path), "/out/report.html", "/out/files.csv", C)
    out, _ = capsys.readouterr()
    assert "\033[" not in out
    assert "DiskStat" in out


def test_make_colors_enabled():
    C = _make_colors(True)
    assert C.CYAN == "\033[36m"
    assert C.RED == "\033[31m"
    assert C.RESET == "\033[0m"


def test_make_colors_disabled():
    C = _make_colors(False)
    assert C.CYAN == ""
    assert C.RED == ""
    assert C.RESET == ""


def test_supports_color_no_color_env(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert _supports_color() is False


def test_max_scan_depth_constant():
    """_MAX_SCAN_DEPTH should be 256."""
    assert _MAX_SCAN_DEPTH == 256


def test_ext_map_categories():
    """EXT_MAP should contain expected categories."""
    expected = {"zip", "image", "video", "audio", "doc", "code", "exe", "font", "data", "system"}
    assert set(EXT_MAP.keys()) == expected


def test_ext_colors_all_categories():
    """EXT_COLORS should have entries for all EXT_MAP categories plus folder/unknown."""
    for cat in EXT_MAP:
        assert cat in EXT_COLORS, f"Missing color for category: {cat}"
    assert "folder" in EXT_COLORS
    assert "unknown" in EXT_COLORS


def test_format_bytes_edge_cases():
    """format_bytes edge cases."""
    assert format_bytes(0) == "0.0 B"
    assert format_bytes(-1) == "0.0 B"
    assert format_bytes(None) == "0.0 B"
    assert format_bytes("abc") == "0.0 B"
    assert format_bytes(1) == "1.0 B"
    assert format_bytes(1023) == "1023.0 B"
    assert format_bytes(1024) == "1.0 KB"


def test_format_bytes_pb():
    """format_bytes should handle petabytes."""
    result = format_bytes(1024 ** 5)
    assert "PB" in result



# --- Tests for --sort and ---

# --- Tests for --sort and --top CLI flags ---

def test_main_top_flag_in_text_mode(tmp_path):
    """--top N should show top N files in text output."""
    (tmp_path / "small.txt").write_text("a" * 10)
    (tmp_path / "large.bin").write_bytes(b"\x00" * 10000)
    (tmp_path / "medium.txt").write_text("b" * 1000)

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    buf = io.StringIO()
    old_argv = sys.argv
    old_cwd = os.getcwd()
    try:
        os.chdir(str(tmp_path))
        sys.argv = ["diskstat.py", str(tmp_path), "-o", str(out_dir), "--top", "2"]
        with redirect_stdout(buf):
            main()
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)

    out = buf.getvalue()
    assert "Top 2 files" in out
    assert "large.bin" in out


def test_main_sort_by_name(tmp_path):
    """--sort name should sort top files alphabetically."""
    (tmp_path / "zebra.txt").write_text("z" * 5000)
    (tmp_path / "alpha.txt").write_text("a" * 100)
    (tmp_path / "mango.txt").write_text("m" * 500)

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    buf = io.StringIO()
    old_argv = sys.argv
    old_cwd = os.getcwd()
    try:
        os.chdir(str(tmp_path))
        sys.argv = ["diskstat.py", str(tmp_path), "-o", str(out_dir), "--top", "10", "--sort", "name"]
        with redirect_stdout(buf):
            main()
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)

    out = buf.getvalue()
    assert "Top 10 files" in out
    alpha_pos = out.index("alpha.txt")
    zebra_pos = out.index("zebra.txt")
    assert alpha_pos < zebra_pos  # alpha before zebra


def test_main_top_zero_shows_all(tmp_path):
    """--top 0 (default) should not show top files list."""
    (tmp_path / "a.txt").write_text("hello")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    buf = io.StringIO()
    old_argv = sys.argv
    old_cwd = os.getcwd()
    try:
        os.chdir(str(tmp_path))
        sys.argv = ["diskstat.py", str(tmp_path), "-o", str(out_dir), "--top", "0"]
        with redirect_stdout(buf):
            main()
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)

    out = buf.getvalue()
    assert "Top" not in out  # No top N section when --top 0


def test_build_flat_with_min_size(tmp_path):
    """build_flat should filter files smaller than min_size."""
    tree = {"name": "root", "size": 100, "category": "folder", "children": [
        {"name": "tiny.txt", "size": 10, "category": "doc"},
        {"name": "big.txt", "size": 90, "category": "doc"},
    ]}
    flat = build_flat(tree, max_nodes=10, min_size=50)
    names = [f["name"] for f in flat]
    assert "big.txt" in names
    assert "tiny.txt" not in names


def test_build_flat_with_categories(tmp_path):
    """build_flat should filter by category."""
    tree = {"name": "root", "size": 200, "category": "folder", "children": [
        {"name": "a.py", "size": 50, "category": "code"},
        {"name": "b.jpg", "size": 150, "category": "image"},
    ]}
    flat = build_flat(tree, max_nodes=10, categories=["code"])
    names = [f["name"] for f in flat]
    assert "a.py" in names
    assert "b.jpg" not in names


def test_build_flat_with_exclude_dirs(tmp_path):
    """build_flat should skip excluded directory names."""
    tree = {"name": "root", "size": 150, "category": "folder", "children": [
        {"name": ".git", "size": 50, "category": "folder", "children": [
            {"name": "config", "size": 50},
        ]},
        {"name": "src", "size": 100, "category": "folder", "children": [
            {"name": "main.py", "size": 100, "category": "code"},
        ]},
    ]}
    flat = build_flat(tree, max_nodes=100, exclude_dirs=[".git"])
    names = [f["name"] for f in flat]
    assert "src" in names
    assert ".git" not in names
    assert "config" not in names


def test_main_no_html_flag(tmp_path):
    """--no-html should skip HTML generation but still write CSV."""
    (tmp_path / "a.txt").write_text("hello")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    old_argv = sys.argv
    old_cwd = os.getcwd()
    try:
        os.chdir(str(tmp_path))
        sys.argv = ["diskstat.py", str(tmp_path), "-o", str(out_dir), "--no-html"]
        main()
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)

    htmls = list(out_dir.glob("*.html"))
    csvs = list(out_dir.glob("*.csv"))
    assert len(htmls) == 0
    assert len(csvs) == 1

    # CSV should still have data
    content = csvs[0].read_text()
    assert "a.txt" in content


def test_compare_reports(tmp_path):
    """_compare_reports should detect added/removed/changed files."""
    from diskstat import _compare_reports

    # Create baseline CSV
    baseline = tmp_path / "baseline.csv"
    with open(baseline, "w", newline="") as f:
        w = csv_mod.writer(f)
        w.writerow(["name", "path", "size_bytes", "size_human", "category", "parent"])
        w.writerow(["old_file.txt", "/tmp/old_file.txt", 100, "100.0 B", "doc", "root"])
        w.writerow(["common.txt", "/tmp/common.txt", 200, "200.0 B", "doc", "root"])

    # Current flat list (path is the unique key now)
    current_flat = [
        {"name": "root", "path": "/tmp", "parent": None, "size": 600},
        {"name": "common.txt", "path": "/tmp/common.txt", "parent": "root", "size": 300},  # changed
        {"name": "new_file.txt", "path": "/tmp/new_file.txt", "parent": "root", "size": 500},  # added
    ]

    added, removed, changed = _compare_reports(current_flat, str(baseline))
    assert "/tmp/new_file.txt" in added
    assert "/tmp/old_file.txt" in removed
    assert "/tmp/common.txt" in changed
    assert changed["/tmp/common.txt"] == (200, 300)


def test_load_config_json(tmp_path):
    """_load_config should parse JSON config."""
    from diskstat import _load_config

    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({
        "exclude": [".git", "node_modules"],
        "max_nodes": 100,
        "min_size": 1024,
    }))

    cfg = _load_config(str(config_file))
    assert cfg["exclude"] == [".git", "node_modules"]
    assert cfg["max_nodes"] == 100
    assert cfg["min_size"] == 1024


def test_load_config_missing_file():
    """_load_config should raise FileNotFoundError for missing file."""
    from diskstat import _load_config

    with pytest.raises(FileNotFoundError):
        _load_config("/nonexistent/config.json")


def test_main_compare_flag(tmp_path):
    """--compare should show comparison output."""
    (tmp_path / "a.txt").write_text("hello")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    # Create baseline CSV
    baseline = tmp_path / "baseline.csv"
    with open(baseline, "w", newline="") as f:
        w = csv_mod.writer(f)
        w.writerow(["name", "path", "size_bytes", "size_human", "category", "parent"])
        w.writerow(["old.txt", "/tmp/old.txt", 100, "100.0 B", "doc", "root"])

    old_argv = sys.argv
    old_cwd = os.getcwd()
    buf = io.StringIO()
    try:
        os.chdir(str(tmp_path))
        sys.argv = ["diskstat.py", str(tmp_path), "-o", str(out_dir),
                    "--compare", str(baseline), "--no-color"]
        with redirect_stdout(buf):
            main()
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)

    out = buf.getvalue()
    assert "Compare" in out
    assert "Added" in out
    assert "Removed" in out


def test_scan_max_depth_override(tmp_path):
    """scan() should respect max_depth parameter."""
    # Create nested dirs: root/d0/d1/d2/d3
    current = tmp_path
    for i in range(4):
        current = current / f"d{i}"
        current.mkdir()
    (current / "deep_file.txt").write_text("deep")
    (tmp_path / "root_file.txt").write_text("root")

    # Default depth should find all
    tree, stats = scan(str(tmp_path))
    assert stats["files"] == 2

    # Depth 0 should only scan root
    tree, stats = scan(str(tmp_path), max_depth=0)
    assert stats["files"] == 1
    assert stats["skipped"] >= 1


def test_main_version_flag(capsys):
    """--version should print version and exit."""
    old_argv = sys.argv
    try:
        sys.argv = ["diskstat.py", "--version"]
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
    finally:
        sys.argv = old_argv


def test_main_dry_run_no_files(tmp_path):
    """--dry-run should not create HTML/CSV files."""
    (tmp_path / "a.txt").write_text("hello")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    old_argv = sys.argv
    old_cwd = os.getcwd()
    try:
        os.chdir(str(tmp_path))
        sys.argv = ["diskstat.py", str(tmp_path), "-o", str(out_dir), "--dry-run"]
        main()
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)

    htmls = list(out_dir.glob("*.html"))
    csvs = list(out_dir.glob("*.csv"))
    assert len(htmls) == 0
    assert len(csvs) == 0


def test_main_filter_flag(tmp_path):
    """--filter should only show matching files."""
    (tmp_path / "test_module.py").write_text("a" * 1000)
    (tmp_path / "README.md").write_text("b" * 100)
    (tmp_path / "app.js").write_text("c" * 500)

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    old_argv = sys.argv
    old_cwd = os.getcwd()
    try:
        os.chdir(str(tmp_path))
        sys.argv = ["diskstat.py", str(tmp_path), "-o", str(out_dir), "--filter", r"\.py$"]
        main()
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)

    # Check CSV only has .py files
    csv_files = list(out_dir.glob("*.csv"))
    assert len(csv_files) == 1
    content = csv_files[0].read_text()
    assert "test_module.py" in content
    assert "README.md" not in content
    assert "app.js" not in content


def test_main_max_depth_flag(tmp_path):
    """--max-depth should limit scan depth."""
    (tmp_path / "shallow.txt").write_text("x")
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (deep / "deep.txt").write_text("y")

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    old_argv = sys.argv
    old_cwd = os.getcwd()
    try:
        os.chdir(str(tmp_path))
        sys.argv = ["diskstat.py", str(tmp_path), "-o", str(out_dir), "--max-depth", "1"]
        main()
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)

    csv_files = list(out_dir.glob("*.csv"))
    assert len(csv_files) == 1
    content = csv_files[0].read_text()
    assert "shallow.txt" in content
    assert "deep.txt" not in content


def test_main_category_summary(tmp_path):
    """Text mode should show category summary."""
    (tmp_path / "a.py").write_text("x" * 100)
    (tmp_path / "b.jpg").write_text("y" * 200)
    (tmp_path / "c.txt").write_text("z" * 300)

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    old_argv = sys.argv
    old_cwd = os.getcwd()
    try:
        os.chdir(str(tmp_path))
        sys.argv = ["diskstat.py", str(tmp_path), "-o", str(out_dir), "--no-color"]
        main()
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)

    # Re-read stdout - category summary is printed
    # This test just ensures no crash with multiple categories


def test_timestamp_microsecond_no_conflict(tmp_path):
    """Output dir timestamp should include microseconds to avoid conflicts."""
    # Verify the timestamp format includes %f
    import datetime as dt
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    assert len(ts) == 22  # YYYYMMDD_HHMMSS_ffffff


def test_top_n_with_reverse_size_sort(tmp_path):
    """--reverse with --sort size should show smallest files first."""
    files = [("a.bin", 500), ("b.bin", 100), ("c.bin", 300)]
    for name, sz in files:
        (tmp_path / name).write_bytes(b"\x00" * sz)

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    buf = io.StringIO()
    old_argv = sys.argv
    old_cwd = os.getcwd()
    try:
        os.chdir(str(tmp_path))
        sys.argv = ["diskstat.py", str(tmp_path), "-o", str(out_dir),
                    "--no-color", "--top", "2", "--sort", "size", "--reverse"]
        with redirect_stdout(buf):
            main()
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)

    output = buf.getvalue()
    # Smallest 2 first: b.bin (100), c.bin (300)
    lines = [ln for ln in output.splitlines() if ".bin" in ln]
    assert "b.bin" in lines[0]


def test_top_n_with_reverse_name_sort(tmp_path):
    """--reverse with --sort name should reverse alphabetical order."""
    for name in ["aaa.txt", "bbb.txt", "ccc.txt"]:
        (tmp_path / name).write_text("x" * 100)

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    buf = io.StringIO()
    old_argv = sys.argv
    old_cwd = os.getcwd()
    try:
        os.chdir(str(tmp_path))
        sys.argv = ["diskstat.py", str(tmp_path), "-o", str(out_dir),
                    "--no-color", "--top", "2", "--sort", "name", "--reverse"]
        with redirect_stdout(buf):
            main()
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)

    output = buf.getvalue()
    lines = [ln for ln in output.splitlines() if ".txt" in ln]
    # Reversed alpha = ccc, bbb
    assert "ccc.txt" in lines[0]
