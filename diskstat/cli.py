"""CLI argument parsing and main() entry point for diskstat."""

from __future__ import annotations

import argparse
import datetime
import os
import re
import sys
import time
from typing import Optional, Pattern

from .config import _load_config, _MAX_SCAN_DEPTH
from .scanner import scan, build_flat, format_bytes
from .renderer import render_html, _open_report
from .reporter import _output_text, _output_json, _compare_reports


def _supports_color() -> bool:
    """Check if stdout supports ANSI colors."""
    if os.getenv("NO_COLOR"):
        return False
    if os.getenv("FORCE_COLOR"):
        return True
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _make_colors(enabled: bool):
    """Return ANSI color codes as a simple namespace-like dict."""
    if enabled:
        return type("C", (), {
            "CYAN": "\033[36m", "GREEN": "\033[32m", "YELLOW": "\033[33m",
            "RED": "\033[31m", "BOLD": "\033[1m", "DIM": "\033[2m", "RESET": "\033[0m",
        })()
    return type("C", (), {
        "CYAN": "", "GREEN": "", "YELLOW": "", "RED": "", "BOLD": "", "DIM": "", "RESET": "",
    })()


def _parse_args() -> argparse.Namespace:
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


def main() -> None:
    """Main entry point for diskstat."""
    # Ensure UTF-8 output on Windows consoles (PyInstaller exe)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    args = _parse_args()

    # Load config file if specified and apply defaults
    config: dict = {}
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

    target: str = args.path
    ts: str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out_dir: str = args.out or os.path.join(os.getcwd(), "diskstat", ts)
    os.makedirs(out_dir, exist_ok=True)
    html_out: str = os.path.join(out_dir, "report.html")
    csv_out: str = os.path.join(out_dir, "files.csv")

    use_color: bool = not args.no_color and _supports_color()
    C = _make_colors(use_color)

    # Compile regex filter if provided
    filter_re: Optional[Pattern] = None
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
        _last_p: dict = {"files": 0, "dirs": 0, "time": time.time()}

        def on_progress(directory: str, files: int, dirs: int) -> None:
            now = time.time()
            if now - _last_p["time"] < 0.5:
                return
            _last_p.update({"files": files, "dirs": dirs, "time": now})
            d = os.path.basename(directory) or directory
            line = f"\r  {C.DIM}...{d}{C.RESET}  {C.CYAN}{files} f{C.RESET}  {C.GREEN}{dirs} d{C.RESET}"
            sys.stdout.write(line[:100].ljust(100))
            sys.stdout.flush()

        print(f"{C.BOLD}DiskStat{C.RESET} -- scanning {C.CYAN}{target}{C.RESET}")
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
