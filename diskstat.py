#!/usr/bin/env python3
"""Disk usage analyzer (WinDirStat-like). Scans a directory, then produces an HTML treemap + CSV report."""

import os, sys, time, datetime, json, csv, pathlib, webbrowser, html as html_mod, subprocess

DEFAULT_TARGET = "/mnt/c/"


EXT_COLORS = {
    "folder": "#1f77b4",
    "unknown": "#cccccc",
    "zip": "#ff7f0e",
    "image": "#9467bd",
    "video": "#d62728",
    "audio": "#8c564b",
    "doc": "#2ca02c",
    "code": "#17becf",
    "exe": "#e377c2",
    "font": "#bcbd22",
    "data": "#7f7f7f",
    "system": "#aec7e8",
}

EXT_MAP = {
    "zip": {".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz", ".tgz", ".lz", ".zst"},
    "image": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".ico", ".avif"},
    "video": {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".m2ts", ".vob"},
    "audio": {".mp3", ".wav", ".aac", ".flac", ".m4a", ".wma", ".ogg", ".opus", ".aiff", ".alac"},
    "doc": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp", ".txt", ".rtf", ".csv", ".md", ".pages", ".key", ".numbers"},
    "code": {".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".cs", ".go", ".rs", ".php", ".rb", ".swift", ".kt", ".scala", ".html", ".css", ".scss", ".less", ".sql", ".sh", ".bat", ".ps1", ".psm1", ".vue", ".jsx", ".tsx", ".json", ".yaml", ".yml", ".toml", ".xml", ".ini", ".cfg", ".conf"},
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
    ext = pathlib.Path(name).suffix.lower()
    for cat, exts in EXT_MAP.items():
        if ext in exts:
            return cat
    return "unknown"


_MAX_SCAN_DEPTH = 256  # prevent runaway recursion from deep nesting


def format_bytes(b):
    if not b or b < 0:
        return "0.0 B"
    if b == 0:
        return "0.0 B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = int(min(len(units) - 1, (b.bit_length() - 1) // 10))
    v = b / (1024 ** i)
    return f"{v:.1f} {units[i]}"


def scan(path: str, on_progress=None):
    # Windows path normalisation is handled by _resolve_path
    try:
        path = _resolve_path(path)
    except (ValueError, OSError):
        return {"name": os.path.basename(path) or path, "path": path, "size": 0, "category": "folder"}, {
            "files": 0, "dirs": 0, "skipped": 1, "elapsed_s": 0, "root": path,
        }
    root_name = os.path.basename(os.path.normpath(path)) or "\\"
    tree = {"name": root_name, "path": path, "size": 0, "category": "folder"}
    t0 = time.time()
    scanned_files = 0
    scanned_dirs = 0
    skipped = 0

    def _walk(directory: str, node: dict, depth: int = 0):
        nonlocal scanned_files, scanned_dirs, skipped
        if depth > _MAX_SCAN_DEPTH:
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
    except (OSError, PermissionError) as e:
        # Target became inaccessible during scan — return empty result
        pass
    return tree, {
        "files": scanned_files,
        "dirs": scanned_dirs,
        "skipped": skipped,
        "elapsed_s": round(time.time() - t0, 3),
        "root": path,
    }


def build_flat(tree, max_nodes: int = 5000):
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
        queue.append((child, tree.get("name", "ROOT")))

    count = 1
    while queue and count < max_nodes:
        node, parent_name = queue.pop(0)
        count += 1
        cat = node.get("category", "folder" if "children" in node else "unknown")
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


def render_html(tree_data, flat, target, output_html, csv_path):
    """Render the WinDirStat-like HTML report from a template file."""
    # Collect sidebar stats
    all_nodes = [n for n in flat if n.get("parent") is not None]
    total_size = sum(n.get("size", 0) for n in all_nodes)
    total_files = sum(1 for n in all_nodes if n.get("category") != "folder")
    total_dirs  = sum(1 for n in all_nodes if n.get("category") == "folder")
    exts = {}
    for n in all_nodes:
        c = n.get("category", "unknown")
        exts[c] = exts.get(c, 0) + 1

    root_name = tree_data.get("name", "ROOT")
    stats_line = "{files} files, {dirs} dirs | {total} total".format(
        files=total_files, dirs=total_dirs, total=format_bytes(total_size)
    )

    # Read template - check several locations
    _here = os.path.dirname(os.path.abspath(__file__))
    _cand_sub = os.path.join(_here, "diskstat", "template.html")
    _cand_root = os.path.join(_here, "template.html")
    _candidates = [_cand_sub, _cand_root]
    template_path = None
    for _p in _candidates:
        if os.path.exists(_p):
            template_path = _p
            break
    if template_path is None:
        raise FileNotFoundError(
            f"template.html not found. Searched: {_candidates}"
        )
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    # XSS guard: user-controlled data must be escaped before HTML injection
    safe_root = html_mod.escape(root_name)
    safe_stats = html_mod.escape(stats_line)

    html = html.replace("__ROOT_NAME__", safe_root)
    html = html.replace("__STATS_LINE__", safe_stats)
    html = html.replace("__JS_FLAT__", json.dumps(flat, ensure_ascii=False))
    html = html.replace("__JS_COLORS__", json.dumps(EXT_COLORS, ensure_ascii=False))

    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html)

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "path", "size_bytes", "size_human", "category", "parent"])
        for row in flat:
            writer.writerow(
                [
                    row.get("name", ""),
                    row.get("path", ""),
                    row.get("size", 0),
                    format_bytes(row.get("size", 0)),
                    row.get("category", "unknown"),
                    row.get("parent", ""),
                ]
            )


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


class _Colors:
    """ANSI color codes (no-op when colors unsupported)."""
    def __init__(self, enabled):
        if enabled:
            self.CYAN = "\033[36m"
            self.GREEN = "\033[32m"
            self.YELLOW = "\033[33m"
            self.RED = "\033[31m"
            self.BOLD = "\033[1m"
            self.DIM = "\033[2m"
            self.RESET = "\033[0m"
        else:
            self.CYAN = self.GREEN = self.YELLOW = self.RED = self.BOLD = self.DIM = self.RESET = ""


def main():
    import argparse

    ap = argparse.ArgumentParser(description="Disk usage analyzer (WinDirStat-like) for Windows/WSL")
    ap.add_argument("path", nargs="?", default="/mnt/c/", help="Path to scan (default: /mnt/c/)")
    ap.add_argument("-o", "--out", default=None, help="Output directory")
    ap.add_argument("--open", action="store_true", help="Open HTML report after generation")
    ap.add_argument("-m", "--max-nodes", type=int, default=5000, help="Max nodes to include in visualization")
    ap.add_argument("--format", choices=["text", "json"], default="text", help="Output format (default: text)")
    ap.add_argument("--no-color", action="store_true", help="Disable colored output")
    ap.add_argument("--progress", action="store_true", help="Show live progress during scan")
    args = ap.parse_args()

    # Clamp max_nodes to a sane range to prevent accidental DoS / OOM
    args.max_nodes = max(1, min(int(args.max_nodes), 500_000))

    target = args.path
    out_dir = args.out or os.path.join(os.getcwd(), "diskstat", datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(out_dir, exist_ok=True)
    html_out = os.path.join(out_dir, "report.html")
    csv_out = os.path.join(out_dir, "files.csv")

    use_color = not args.no_color and _supports_color()
    C = _Colors(use_color)

    if args.format == "json":
        # JSON mode: structured output, no colors
        def on_progress(directory, files, dirs):
            pass  # no progress in JSON mode

        tree, stats = scan(target, on_progress=on_progress if args.progress else None)
        total = tree.get("size", 0)
        flat = build_flat(tree, max_nodes=int(args.max_nodes))
        render_html(tree, flat, target, html_out, csv_out)

        result = {
            "ok": True,
            "target": os.path.realpath(target),
            "stats": stats,
            "total_bytes": total,
            "total_human": format_bytes(total),
            "nodes_included": len(flat),
            "output": {
                "html": html_out,
                "csv": csv_out,
            },
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        # Text mode: human-readable with optional colors + progress
        _last_progress = {"files": 0, "dirs": 0, "time": time.time()}

        def on_progress(directory, files, dirs):
            now = time.time()
            if now - _last_progress["time"] < 0.5:
                return  # throttle to 2 updates/sec
            _last_progress.update({"files": files, "dirs": dirs, "time": now})
            d = os.path.basename(directory) or directory
            line = f"  {C.DIM}...{d}{C.RESET}  {C.CYAN}{files} files{C.RESET}  {C.GREEN}{dirs} dirs{C.RESET}"
            # Overwrite current line
            sys.stdout.write("\r" + line[:100].ljust(100))
            sys.stdout.flush()

        print(f"{C.BOLD}DiskStat{C.RESET} — scanning {C.CYAN}{os.path.realpath(target)}{C.RESET}")
        tree, stats = scan(target, on_progress=on_progress if args.progress else None)
        total = tree.get("size", 0)

        # Clear progress line
        if args.progress:
            sys.stdout.write("\r" + " " * 100 + "\r")
            sys.stdout.flush()

        print(f"{C.GREEN}✓{C.RESET} Done in {C.BOLD}{stats['elapsed_s']}s{C.RESET}")
        print(f"  {stats['dirs']} dirs  {stats['files']} files  {stats['skipped']} skipped  {C.BOLD}{format_bytes(total)}{C.RESET} total")

        flat = build_flat(tree, max_nodes=int(args.max_nodes))
        render_html(tree, flat, target, html_out, csv_out)
        print(f"  {C.CYAN}HTML{C.RESET} : {html_out}")
        print(f"  {C.CYAN}CSV {C.RESET} : {csv_out}")
    if args.open:
        # WSL: use cmd.exe /c start (opens in Windows browser)
        # Fallback: xdg-open on Linux native
        if os.path.exists("/mnt/c/Windows/System32/cmd.exe"):
            cmd_path = "/mnt/c/Windows/System32/cmd.exe"
            html_win = html_out.replace("/mnt/c/", "C:\\").replace("/", "\\")
            subprocess.run([cmd_path, "/c", "start", "", html_win], shell=False)
        else:
            webbrowser.open("file://" + html_out)


if __name__ == "__main__":
    main()
