#!/usr/bin/env python3
"""Disk usage analyzer (WinDirStat-like). Scans a directory, then produces an HTML treemap + CSV report."""

import os
import re
import sys
import time
import datetime
import json
import csv
import webbrowser
import html as html_mod
import subprocess
import argparse


EXT_COLORS = {
    "folder": "#E8D4A0",
    "unknown": "#C0C0B8",
    "zip": "#D08030",
    "image": "#9060B0",
    "video": "#B04040",
    "audio": "#806040",
    "doc": "#509050",
    "code": "#3080A0",
    "exe": "#A05080",
    "font": "#908050",
    "data": "#707068",
    "system": "#6080A0",
}

EXT_MAP = {
    "zip": {".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz", ".tgz", ".lz", ".zst"},
    "image": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".ico", ".avif"},
    "video": {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".m2ts", ".vob"},
    "audio": {".mp3", ".wav", ".aac", ".flac", ".m4a", ".wma", ".ogg", ".opus", ".aiff", ".alac"},
    "doc": {
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".odt", ".ods", ".odp", ".txt", ".rtf", ".csv", ".md",
        ".pages", ".key", ".numbers",
    },
    "code": {
        ".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".cs", ".go", ".rs",
        ".php", ".rb", ".swift", ".kt", ".scala", ".html", ".css", ".scss",
        ".less", ".sql", ".sh", ".bat", ".ps1", ".psm1", ".vue", ".jsx",
        ".tsx", ".json", ".yaml", ".yml", ".toml", ".xml", ".ini", ".cfg", ".conf",
    },
    "exe": {".exe", ".dll", ".so", ".dylib", ".bin", ".msi", ".app", ".apk", ".ipa"},
    "font": {".ttf", ".otf", ".woff", ".woff2", ".eot", ".fnt", ".fon"},
    "data": {".db", ".sqlite", ".sqlite3", ".mdb", ".accdb", ".dat", ".log", ".iso", ".img", ".bak", ".tmp", ".cache"},
    "system": {".sys", ".lnk", ".url", ".reg", ".cab"},
}


def _resolve_path(p: str) -> str:
    """Resolve and validate a path for scanning.

    - Expands ~
    - Resolves symlinks (so we report on the real target)
    - Must exist and be a directory
    - Returns real absolute path
    """
    p = os.path.expanduser(p)
    p = os.path.realpath(p)  # resolve symlinks
    if not os.path.exists(p):
        raise ValueError(f"Path does not exist: {p}")
    if not os.path.isdir(p):
        raise ValueError(f"Path is not a directory: {p}")
    if not os.access(p, os.R_OK):
        raise ValueError(f"Path is not readable: {p}")
    return p


def ext_category(name, is_dir=False):
    if is_dir:
        return "folder"
    ext = os.path.splitext(name)[1].lower()
    for cat, exts in EXT_MAP.items():
        if ext in exts:
            return cat
    return "unknown"


_MAX_SCAN_DEPTH = 256  # prevent runaway recursion from deep nesting


def format_bytes(b):
    if not isinstance(b, (int, float)):
        return "0.0 B"
    if b <= 0:
        return "0.0 B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = int(min(len(units) - 1, (int(b).bit_length() - 1) // 10))
    v = b / (1024 ** i)
    return f"{v:.1f} {units[i]}"


def scan(path: str, on_progress=None, max_depth=None):
    """Scan directory tree. Returns (tree, stats).

    Args:
        path: directory to scan
        on_progress: optional callback(directory, files, dirs)
        max_depth: override default max recursion depth
    """
    _depth_limit = max_depth if max_depth is not None else _MAX_SCAN_DEPTH
    # Windows path normalisation is handled by _resolve_path
    try:
        path = _resolve_path(path)
    except (ValueError, OSError):
        return {"name": os.path.basename(path) or path, "path": path, "size": 0, "category": "folder"}, {
            "files": 0, "dirs": 0, "skipped": 1, "elapsed_s": 0, "root": path,
        }
    root_name = os.path.basename(path) or path
    tree = {"name": root_name, "path": path, "size": 0, "category": "folder"}
    t0 = time.time()
    scanned_files = 0
    scanned_dirs = 0
    skipped = 0

    def _walk(directory: str, node: dict, depth: int = 0):
        nonlocal scanned_files, scanned_dirs, skipped
        if depth > _depth_limit:
            skipped += 1
            return 0
        if on_progress:
            on_progress(directory, scanned_files, scanned_dirs)
        try:
            entries = sorted(os.scandir(directory), key=lambda e: e.name)
        except (OSError, PermissionError):
            skipped += 1
            return 0
        size = 0
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    scanned_dirs += 1
                    child = {
                        "name": entry.name,
                        "path": os.path.join(directory, entry.name),
                        "size": 0,
                        "category": "folder",
                        "children": [],
                    }
                    node.setdefault("children", []).append(child)
                    size += _walk(entry.path, child, depth + 1)
                elif entry.is_file(follow_symlinks=False):
                    try:
                        sz = entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        sz = 0
                    scanned_files += 1
                    node.setdefault("children", []).append(
                        {
                            "name": entry.name,
                            "path": os.path.join(directory, entry.name),
                            "size": sz,
                            "category": ext_category(entry.name, is_dir=False),
                        }
                    )
                    size += sz
            except (OSError, PermissionError):
                skipped += 1
                continue
        node["size"] = size
        return size

    # If the target was deleted between validation and scan, handle gracefully
    try:
        _walk(path, tree)
    except (OSError, PermissionError):
        # Target became inaccessible during scan — return empty result
        pass
    return tree, {
        "files": scanned_files,
        "dirs": scanned_dirs,
        "skipped": skipped,
        "elapsed_s": round(max(0.0, time.time() - t0), 3),
        "root": path,
    }


def build_flat(tree, max_nodes=5000, min_size=0, categories=None, exclude_dirs=None):
    """Flatten tree to a list of nodes for visualization.

    Args:
        tree: nested dict from scan()
        max_nodes: max nodes to include
        min_size: minimum file size in bytes (files smaller are skipped)
        categories: set of category names to include (None = all)
        exclude_dirs: set of directory names to skip (None = none)
    """
    if categories is not None:
        categories = set(categories)
    if exclude_dirs is not None:
        exclude_dirs = set(exclude_dirs)
    out = [
        {
            "name": tree.get("name", "ROOT"),
            "path": tree.get("path", ""),
            "size": tree.get("size", 0),
            "category": "folder",
            "parent": None,
        }
    ]
    if max_nodes <= 1:
        return out

    # BFS over children, sorted by size descending at each level
    queue = []
    children = tree.get("children", [])
    children.sort(key=lambda x: x.get("size", 0), reverse=True)
    for child in children:
        cname = child.get("name", "")
        ccat = child.get("category", "folder" if "children" in child else "unknown")
        # Skip excluded dirs
        if exclude_dirs and cname in exclude_dirs and ccat == "folder":
            continue
        # Skip by category filter (always keep folders for traversal)
        if categories and ccat not in categories and ccat != "folder":
            continue
        queue.append((child, tree.get("name", "ROOT")))

    count = 1
    while queue and count < max_nodes:
        node, parent_name = queue.pop(0)
        count += 1
        cat = node.get("category", "folder" if "children" in node else "unknown")

        # Apply filters
        if min_size > 0 and cat != "folder" and node.get("size", 0) < min_size:
            count -= 1  # don't count filtered files
            continue
        if categories and cat not in categories:
            count -= 1
            continue

        out.append(
            {
                "name": node.get("name", "?"),
                "path": node.get("path", ""),
                "size": node.get("size", 0),
                "parent": parent_name,
                "category": cat,
            }
        )
        if count >= max_nodes:
            break
        kids = node.get("children", [])
        if kids:
            kids.sort(key=lambda x: x.get("size", 0), reverse=True)
            for kid in kids:
                queue.append((kid, node.get("name", "?")))

    return out


def _find_template():
    """Locate template.html — checks submodule then project root."""
    here = os.path.dirname(os.path.abspath(__file__))
    _candidates = [
        os.path.join(here, "diskstat", "template.html"),
        os.path.join(here, "template.html"),
    ]
    for p in _candidates:
        if os.path.exists(p):
            return p
    raise FileNotFoundError(f"template.html not found. Searched: {_candidates}")


def _render_template(template_path, root_name, stats_line, flat, colors):
    """Render template with placeholder substitution + XSS protection."""
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()
    # Escape user-controlled values to prevent XSS
    # CSP meta tag in template provides additional defense-in-depth
    html = html.replace("__ROOT_NAME__", html_mod.escape(root_name))
    html = html.replace("__STATS_LINE__", html_mod.escape(stats_line))
    # JSON output is safe: no <script> injection possible via json.dumps
    html = html.replace("__JS_FLAT__", json.dumps(flat, ensure_ascii=False))
    html = html.replace("__JS_COLORS__", json.dumps(colors, ensure_ascii=False))
    return html


def _write_csv(flat, csv_path):
    """Write flat node list to CSV."""
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "path", "size_bytes", "size_human", "category", "parent"])
        for row in flat:
            w.writerow([
                row.get("name", ""),
                row.get("path", ""),
                row.get("size", 0),
                format_bytes(row.get("size", 0)),
                row.get("category", "unknown"),
                row.get("parent", ""),
            ])


def render_html(tree_data, flat, output_html, csv_path, skip_html=False):
    """Render the WinDirStat-like HTML report from a template file."""
    all_nodes = [n for n in flat if n.get("parent") is not None]
    total_size = sum(n.get("size", 0) for n in all_nodes)
    total_files = sum(1 for n in all_nodes if n.get("category") != "folder")
    total_dirs = sum(1 for n in all_nodes if n.get("category") == "folder")

    root_name = tree_data.get("name", "ROOT")
    stats_line = "{files} files, {dirs} dirs | {total} total".format(
        files=total_files, dirs=total_dirs, total=format_bytes(total_size)
    )

    if not skip_html:
        template_path = _find_template()
        html = _render_template(template_path, root_name, stats_line, flat, EXT_COLORS)
        with open(output_html, "w", encoding="utf-8") as f:
            f.write(html)

    _write_csv(flat, csv_path)


def _supports_color():
    """Check if stdout supports ANSI colors."""
    if os.getenv("NO_COLOR"):
        return False
    if os.getenv("FORCE_COLOR"):
        return True
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _make_colors(enabled):
    """Return ANSI color codes as a simple namespace-like dict."""
    if enabled:
        return type("C", (), {
            "CYAN": "\033[36m", "GREEN": "\033[32m", "YELLOW": "\033[33m",
            "RED": "\033[31m", "BOLD": "\033[1m", "DIM": "\033[2m", "RESET": "\033[0m",
        })()
    return type("C", (), {
        "CYAN": "", "GREEN": "", "YELLOW": "", "RED": "", "BOLD": "", "DIM": "", "RESET": "",
    })()


def _load_config(path):
    """Load config from YAML or JSON file. Returns dict of settings."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        if path.endswith((".yaml", ".yml")):
            try:
                import yaml
                return yaml.safe_load(f) or {}
            except ImportError:
                raise ImportError("PyYAML required for .yaml config: pip install pyyaml")
        else:
            return json.load(f)


def _parse_args():
    ap = argparse.ArgumentParser(description="Disk usage analyzer (WinDirStat-like) for Windows/WSL")
    ap.add_argument("path", nargs="?", default="/mnt/c/", help="Path to scan (default: /mnt/c/)")
    ap.add_argument("-o", "--out", default=None, help="Output directory")
    ap.add_argument("--open", action="store_true", help="Open HTML report after generation")
    ap.add_argument("-m", "--max-nodes", type=int, default=5000,
                    help="Max nodes to include in visualization")
    ap.add_argument("--format", choices=["text", "json"], default="text",
                    help="Output format (default: text)")
    ap.add_argument("--no-color", action="store_true", help="Disable colored output")
    ap.add_argument("--progress", action="store_true", help="Show live progress during scan")
    ap.add_argument("--min-size", type=int, default=0,
                    help="Minimum file size in bytes (default: 0)")
    ap.add_argument("--category", action="append", default=[],
                    help="Filter by category (can repeat)")
    ap.add_argument("--exclude", action="append", default=[],
                    help="Exclude dir names (can repeat: .git, node_modules)")
    ap.add_argument("--sort", choices=["size", "name"], default="size",
                    help="Sort flat list by size or name (default: size)")
    ap.add_argument("--top", type=int, default=0,
                    help="Show only top N largest files (0 = all)")
    ap.add_argument("--filter", type=str, default=None,
                    help="Regex pattern to filter file names (case-insensitive)")
    ap.add_argument("--max-depth", type=int, default=_MAX_SCAN_DEPTH,
                    help=f"Max scan depth (default: {_MAX_SCAN_DEPTH})")
    ap.add_argument("--dry-run", action="store_true",
                    help="Scan only, do not write HTML/CSV files")
    ap.add_argument("--no-html", action="store_true",
                    help="Skip HTML report generation (CSV only)")
    ap.add_argument("--config", type=str, default=None,
                    help="Path to YAML/JSON config file with default settings")
    ap.add_argument("--compare", type=str, default=None,
                    help="Path to baseline CSV to compare against (shows added/removed/changed)")
    ap.add_argument("--reverse", action="store_true",
                    help="Reverse sort order (smallest first)")
    ap.add_argument("--version", action="version", version="%(prog)s 1.2.0")
    args = ap.parse_args()
    args.max_nodes = max(1, min(int(args.max_nodes), 500_000))
    args.min_size = max(0, args.min_size)
    if args.top < 0:
        args.top = 0
    if args.max_depth < 1:
        args.max_depth = 1
    return args


def _compare_reports(current_flat, baseline_path):
    """Compare current scan against a baseline CSV. Returns (added, removed, changed)."""
    if not os.path.isfile(baseline_path):
        raise FileNotFoundError(f"Baseline not found: {baseline_path}")

    # Build lookup: path -> size from current (path is unique, name is not)
    current = {n["path"]: n["size"] for n in current_flat if n.get("parent") is not None and n.get("path")}

    # Read baseline
    baseline = {}
    with open(baseline_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            path = row.get("path", "")
            try:
                size = int(row.get("size_bytes", 0))
            except ValueError:
                size = 0
            baseline[path] = size

    added = {k: current[k] for k in current if k not in baseline}
    removed = {k: baseline[k] for k in baseline if k not in current}
    changed = {}
    for k in current:
        if k in baseline and current[k] != baseline[k]:
            changed[k] = (baseline[k], current[k])

    return added, removed, changed


def _output_json(tree, stats, flat, target, html_out, csv_out, dry_run=False):
    total = tree.get("size", 0)
    result = {
        "ok": True,
        "target": stats.get("root", target),
        "stats": stats,
        "total_bytes": total,
        "total_human": format_bytes(total),
        "nodes_included": len(flat),
    }
    if dry_run:
        result["dry_run"] = True
    else:
        result["output"] = {"html": html_out, "csv": csv_out}
    print(json.dumps(result, indent=2, ensure_ascii=False))


def _output_text(stats, target, html_out, csv_out, C):
    total = stats.get("total_bytes", 0)
    root = stats.get("root", target)
    done_mark = "OK" if C.GREEN == "" else "✓"
    print(f"{C.BOLD}DiskStat{C.RESET} — {C.CYAN}{root}{C.RESET}")
    print(f"{C.GREEN}{done_mark}{C.RESET} Done in {C.BOLD}{stats['elapsed_s']}s{C.RESET}")
    print(f"  {stats['dirs']} dirs  {stats['files']} files  "
          f"{stats['skipped']} skipped  {C.BOLD}{format_bytes(total)}{C.RESET} total")
    print(f"  {C.CYAN}HTML{C.RESET} : {html_out}")
    print(f"  {C.CYAN}CSV {C.RESET} : {csv_out}")


def _open_report(html_out):
    """Open HTML report in browser. Handles WSL->Windows path conversion."""
    # WSL: convert /mnt/X/... paths to X:\... for cmd.exe
    html_win = html_out
    for mnt_letter in "cdefghijklmnopqrstuvwxyz":
        prefix = f"/mnt/{mnt_letter}/"
        if html_out.startswith(prefix):
            html_win = html_out.replace(prefix, f"{mnt_letter.upper()}:\\").replace("/", "\\")
            break
    else:
        # Not under /mnt/ — use file:// URL
        html_win = "file://" + html_out

    if os.path.exists("/mnt/c/Windows/System32/cmd.exe"):
        cmd_path = "/mnt/c/Windows/System32/cmd.exe"
        subprocess.run([cmd_path, "/c", "start", "", html_win], shell=False)
    else:
        webbrowser.open(html_win)


def main():
    # Ensure UTF-8 output on Windows consoles (PyInstaller exe)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    args = _parse_args()

    # Load config file if specified and apply defaults
    config = {}
    if args.config:
        try:
            config = _load_config(args.config)
        except (FileNotFoundError, ImportError) as exc:
            print(f"Config error: {exc}", file=sys.stderr)
            sys.exit(1)

    # Config values fill in missing args (CLI flags always override)
    if not args.exclude and config.get("exclude"):
        args.exclude = config["exclude"]
    if not args.category and config.get("category"):
        args.category = config["category"]
    if args.max_nodes == 5000 and config.get("max_nodes"):
        args.max_nodes = int(config["max_nodes"])
    if args.min_size == 0 and config.get("min_size"):
        args.min_size = int(config["min_size"])
    if args.max_depth == _MAX_SCAN_DEPTH and config.get("max_depth"):
        args.max_depth = int(config["max_depth"])

    target = args.path
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out_dir = args.out or os.path.join(os.getcwd(), "diskstat", ts)
    os.makedirs(out_dir, exist_ok=True)
    html_out = os.path.join(out_dir, "report.html")
    csv_out = os.path.join(out_dir, "files.csv")

    use_color = not args.no_color and _supports_color()
    C = _make_colors(use_color)

    # Compile regex filter if provided
    filter_re = None
    if args.filter:
        try:
            filter_re = re.compile(args.filter, re.IGNORECASE)
        except re.error as exc:
            print(f"Invalid regex: {exc}", file=sys.stderr)
            sys.exit(1)

    if args.format == "json":
        tree, stats = scan(target, max_depth=args.max_depth)
        flat = build_flat(
            tree,
            max_nodes=int(args.max_nodes),
            min_size=args.min_size,
            categories=args.category or None,
            exclude_dirs=args.exclude or None,
        )
        if not args.dry_run:
            render_html(tree, flat, html_out, csv_out, skip_html=args.no_html)
        stats["total_bytes"] = tree.get("size", 0)
        _output_json(tree, stats, flat, target, html_out, csv_out, dry_run=args.dry_run)
    else:
        # Text mode
        _last_p = {"files": 0, "dirs": 0, "time": time.time()}

        def on_progress(directory, files, dirs):
            now = time.time()
            if now - _last_p["time"] < 0.5:
                return
            _last_p.update({"files": files, "dirs": dirs, "time": now})
            d = os.path.basename(directory) or directory
            line = f"\r  {C.DIM}...{d}{C.RESET}  {C.CYAN}{files} f{C.RESET}  {C.GREEN}{dirs} d{C.RESET}"
            sys.stdout.write(line[:100].ljust(100))
            sys.stdout.flush()

        print(f"{C.BOLD}DiskStat{C.RESET} — scanning {C.CYAN}{target}{C.RESET}")
        cb = on_progress if args.progress else None
        tree, stats = scan(target, on_progress=cb, max_depth=args.max_depth)

        if args.progress:
            sys.stdout.write("\r" + " " * 100 + "\r")
            sys.stdout.flush()

        flat = build_flat(
            tree,
            max_nodes=int(args.max_nodes),
            min_size=args.min_size,
            categories=args.category or None,
            exclude_dirs=args.exclude or None,
        )

        # Apply regex filter to flat list
        if filter_re:
            flat = [n for n in flat if n.get("parent") is None or filter_re.search(n.get("name", ""))]

        if not args.dry_run:
            render_html(tree, flat, html_out, csv_out, skip_html=args.no_html)

        stats["total_bytes"] = tree.get("size", 0)
        stats["filter"] = args.filter
        _output_text(stats, target, html_out, csv_out, C)

        # Category summary in text mode
        all_nodes = [n for n in flat if n.get("parent") is not None]
        if all_nodes:
            cats: dict[str, int] = {}
            for n in all_nodes:
                c = n.get("category", "unknown")
                cats[c] = cats.get(c, 0) + 1
            print(f"\n{C.BOLD}Categories:{C.RESET}")
            for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
                print(f"  {C.CYAN}{cat:>10}{C.RESET}: {cnt:>6} nodes")

        # Show top N files in text mode
        if args.top > 0 and flat:
            files_only = [n for n in flat if n.get("category") != "folder" and n.get("parent") is not None]
            if args.sort == "name":
                files_only.sort(key=lambda n: n.get("name", "").lower())
                if args.reverse:
                    files_only.reverse()
            else:
                files_only.sort(key=lambda n: n.get("size", 0), reverse=not args.reverse)
            top_n = files_only[:args.top]
            print(f"\n{C.BOLD}Top {args.top} files (--sort {args.sort}):{C.RESET}")
            for i, n in enumerate(top_n, 1):
                size_str = format_bytes(n.get("size", 0))
                print(f"  {C.CYAN}{i:>4}{C.RESET}. {size_str:>12}  {n.get('name', '?')}")

        # Compare against baseline if requested
        if args.compare:
            try:
                added, removed, changed = _compare_reports(flat, args.compare)
            except FileNotFoundError as exc:
                print(f"\n{C.RED}Compare error: {exc}{C.RESET}")
            else:
                total_add = sum(added.values())
                total_rem = sum(removed.values())
                total_chg = sum(abs(c[1] - c[0]) for c in changed.values())
                print(f"\n{C.BOLD}Compare vs {args.compare}:{C.RESET}")
                print(f"  {C.GREEN}Added:{C.RESET}   {len(added):>5} files  {format_bytes(total_add)}")
                print(f"  {C.RED}Removed:{C.RESET} {len(removed):>5} files  {format_bytes(total_rem)}")
                print(f"  {C.YELLOW}Changed:{C.RESET} {len(changed):>5} files  {format_bytes(total_chg)}")
                if added:
                    print(f"\n  {C.GREEN}New files (top 5):{C.RESET}")
                    adder = sorted(added.items(), key=lambda x: -x[1])
                    if args.reverse:
                        adder = adder[::-1]
                    for name, size in adder[:5]:
                        print(f"    {format_bytes(size):>12}  {name}")
                if changed:
                    print(f"\n  {C.YELLOW}Changed (top 5 by delta):{C.RESET}")
                    top_chg = sorted(changed.items(), key=lambda x: abs(x[1][1] - x[1][0]), reverse=not args.reverse)[:5]
                    for name, (old, new_sz) in top_chg:
                        delta = new_sz - old
                        sign = "+" if delta >= 0 else "-"
                        print(f"    {sign}{format_bytes(abs(delta)):>12}  {name}")

    if args.open:
        _open_report(html_out)


if __name__ == "__main__":
    main()
