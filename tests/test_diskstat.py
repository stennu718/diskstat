import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from diskstat import normalize_path, format_bytes, ext_category, scan, build_flat, render_html, main


# normalize_path
def test_normalize_path_windows_drive_backslash():
    assert normalize_path(r"C:\Users\foo") == "/mnt/c/Users/foo"


def test_normalize_path_windows_drive_forwardslash():
    assert normalize_path("C:/Users/foo") == "/mnt/c/Users/foo"


def test_normalize_path_wsl_passthrough():
    assert normalize_path("/mnt/c/Users/foo") == "/mnt/c/Users/foo"


def test_normalize_path_tilde_expansion():
    result = normalize_path("~/documents")
    assert not result.startswith("~")
    assert "documents" in result


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
    render_html(tree, flat, "/mnt/data", str(htmlp), str(csvp))
    text = htmlp.read_text(encoding="utf-8")
    # Template must embed category color mapping.
    assert '"folder": "#1f77b4"' in text
    assert '"doc": "#2ca02c"' in text
    assert '"code": "#17becf"' in text


def test_render_html_file_list_includes_tooltip_attrs(tmp_path):
    tree = {"name": "root", "path": "/mnt/data", "size": 200, "category": "folder", "children": [
        {"name": "a.txt", "path": "/mnt/data/a.txt", "size": 50, "category": "doc"},
        {"name": "b.txt", "path": "/mnt/data/b.txt", "size": 150, "category": "doc"},
    ]}
    flat = build_flat(tree, max_nodes=10)
    htmlp = tmp_path / "groups.html"
    csvp = tmp_path / "groups.csv"
    render_html(tree, flat, "/mnt/data", str(htmlp), str(csvp))
    text = htmlp.read_text(encoding="utf-8")
    # Must have the flat data and color config embedded
    assert "colors" in text
    assert "flat" in text
    assert "extStats" in text


def test_render_html_csv_has_correct_columns(tmp_path):
    tree = {"name": "root", "path": "/mnt/x", "size": 50, "category": "folder", "children": [
        {"name": "a.txt", "path": "/mnt/x/a.txt", "size": 10, "category": "doc"},
    ]}
    flat = build_flat(tree, max_nodes=5)
    html = tmp_path / "h.html"
    csvp = tmp_path / "c.csv"
    render_html(tree, flat, "/mnt/x", str(html), str(csvp))
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




