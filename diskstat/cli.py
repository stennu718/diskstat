"""CLI argument parsing and main() entry point for diskstat."""

from __future__ import annotations

import argparse
import datetime
import os
import re
import sys
import time
from typing import IO, Optional, Pattern

from .config import load_config, _MAX_SCAN_DEPTH  # noqa: F401
from .scanner import scan, build_flat, format_bytes
from .renderer import render_html, _open_report
from .reporter import (
    _output_text, _output_json, _output_csv, _output_tsv, _output_html_table,
    _compare_reports,
)
from .logging_ import setup_logging, VerbosityLevel, get_logger


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
    ap = argparse.ArgumentParser(
        prog="diskstat",
        description="Disk usage analyzer (WinDirStat-like) with interactive treemap + CSV reports",
        epilog="Examples:\n"
               "  diskstat /home --progress\n"
               "  diskstat . --format json | jq .\n"
               "  du -sb * | diskstat --stdin\n"
               "  diskstat /data --config ~/.config/diskstat/config.yaml\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("path", nargs="?", default=None,
                    help="Path to scan (default: current directory; ignored with --stdin)")
    ap.add_argument("-o", "--out", default=None, help="Output directory")
    ap.add_argument("--open", action="store_true", help="Open HTML report after generation")
    ap.add_argument("-m", "--max-nodes", type=int, default=None,
                    help="Max nodes to include in visualization")
    ap.add_argument("--format", choices=["text", "json", "csv", "tsv", "html"], default=None,
                    help="Output format (default: text)")
    ap.add_argument("--no-color", action="store_true", help="Disable colored output")
    ap.add_argument("--progress", action="store_true", help="Show live progress during scan")
    ap.add_argument("--min-size", type=int, default=None,
                    help="Minimum file size in bytes (default: 0)")
    ap.add_argument("--category", action="append", default=[],
                    help="Filter by category (can repeat)")
    ap.add_argument("--exclude", action="append", default=[],
                    help="Exclude dir names (can repeat: .git, node_modules)")
    ap.add_argument("--sort", choices=["size", "name"], default=None,
                    help="Sort flat list by size or name (default: size)")
    ap.add_argument("--top", type=int, default=None,
                    help="Show only top N largest files (0 = all)")
    ap.add_argument("--filter", type=str, default=None,
                    help="Regex pattern to filter file names (case-insensitive)")
    ap.add_argument("--max-depth", type=int, default=None,
                    help=f"Max scan depth (default: {_MAX_SCAN_DEPTH})")
    ap.add_argument("--dry-run", action="store_true",
                    help="Scan only, do not write HTML/CSV files")
    ap.add_argument("--no-html", action="store_true",
                    help="Skip HTML report generation (CSV only)")
    ap.add_argument("--config", type=str, default=None,
                    help="Path to YAML/JSON config file with default settings")
    ap.add_argument("--compare", type=str, default=None,
                    help="Path to baseline CSV to compare against (shows added/removed/changed)")
    ap.add_argument("--stdin", action="store_true",
                    help="Read paths from stdin (one per line)")
    ap.add_argument("-v", "--verbose", action="count", default=0,
                    help="Increase output verbosity (use -vv for debug)")
    ap.add_argument("-q", "--quiet", action="store_true",
                    help="Suppress all output except errors")
    ap.add_argument("--log-file", type=str, default=None,
                    help="Write structured JSON log to file")
    ap.add_argument("--reverse", action="store_true",
                    help="Reverse sort order (smallest first)")
    ap.add_argument("--version", action="version", version="%(prog)s 1.2.0")
    args = ap.parse_args()

    # Apply defaults and clamp values
    if args.max_nodes is not None:
        args.max_nodes = max(1, min(int(args.max_nodes), 500_000))
    if args.min_size is not None:
        args.min_size = max(0, args.min_size)
    if args.top is not None and args.top < 0:
        args.top = 0
    if args.max_depth is not None and args.max_depth < 1:
        args.max_depth = 1

    return args


def _read_stdin_paths() -> list[str]:
    """Read paths from stdin, one per line."""
    paths: list[str] = []
    for line in sys.stdin:
        p = line.strip()
        if p:
            paths.append(p)
    return paths


def _make_progress_bar(enabled: bool, logger):
    """Return a progress callback if enabled."""
    if not enabled:
        return None

    try:
        from tqdm import tqdm
        pbar: Optional[tqdm] = None
        last_count = [0]

        def on_progress(directory: str, files: int, dirs: int) -> None:
            nonlocal pbar, last_count
            if pbar is None:
                pbar = tqdm(desc="Scanning", unit="files", leave=False)
            delta = files - last_count[0]
            if delta > 0:
                pbar.update(delta)
                last_count[0] = files
            pbar.set_postfix_str(f"{dirs} dirs", refresh=False)

        return on_progress
    except ImportError:
        # Fallback: simple stderr progress
        last_t = [time.time()]

        def on_progress(directory: str, files: int, dirs: int) -> None:
            now = time.time()
            if now - last_t[0] < 0.5:
                return
            last_t[0] = now
            d = os.path.basename(directory) or directory
            sys.stderr.write(f"\r  ...{d}  {files} f  {dirs} d")
            sys.stderr.flush()

        return on_progress


def main() -> None:
    """Main entry point for diskstat."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    args = _parse_args()

    # Setup logging
    log_level = VerbosityLevel.from_flags(args.verbose, args.quiet)
    logger = setup_logging(level=log_level, log_file=args.log_file)

    # Load config (XDG-compliant)
    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError, ImportError) as exc:
        logger.error(f"Config error: {exc}")
        sys.exit(1)

    # Config values fill in missing args (CLI flags always override)
    if args.exclude == [] and config.get("exclude"):
        args.exclude = config["exclude"]
    if args.category == [] and config.get("category"):
        args.category = config["category"]
    if args.max_nodes is None and config.get("max_nodes"):
        args.max_nodes = int(config["max_nodes"])
    if args.min_size is None and config.get("min_size"):
        args.min_size = int(config["min_size"])
    if args.max_depth is None and config.get("max_depth"):
        args.max_depth = int(config["max_depth"])
    if args.sort is None and config.get("sort"):
        args.sort = config["sort"]
    if args.top is None and config.get("top"):
        args.top = int(config["top"])
    if args.filter is None and config.get("filter"):
        args.filter = config["filter"]
    if args.format is None and config.get("format"):
        args.format = config["format"]
    if not args.no_color and config.get("no_color"):
        args.no_color = True
    if not args.progress and config.get("progress"):
        args.progress = True
    if not args.no_html and config.get("no_html"):
        args.no_html = True

    # Apply defaults for remaining None values
    if args.max_nodes is None:
        args.max_nodes = 5000
    if args.min_size is None:
        args.min_size = 0
    if args.sort is None:
        args.sort = "size"
    if args.top is None:
        args.top = 0
    if args.format is None:
        args.format = "text"

    # Handle stdin mode
    if args.stdin:
        paths = _read_stdin_paths()
        if not paths:
            logger.error("No paths provided on stdin")
            sys.exit(1)
        _run_on_paths(args, paths, logger)
        return

    target: str = args.path or "."
    _run_on_paths(args, [target], logger)


def _run_on_paths(args, paths: list[str], logger) -> None:
    """Run scan on one or more paths."""
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
            logger.error(f"Invalid regex: {exc}")
            sys.exit(1)

    # Progress callback
    progress_cb = _make_progress_bar(args.progress, logger)

    # Determine scan target
    if len(paths) == 1:
        target = paths[0]
    else:
        target = f"{len(paths)} paths"

    if args.format != "json" and not args.quiet:
        print(f"{C.BOLD}DiskStat{C.RESET} -- scanning {C.CYAN}{target}{C.RESET}")

    # Scan all paths
    all_flat: list[dict] = []
    combined_stats = {"files": 0, "dirs": 0, "skipped": 0, "elapsed_s": 0, "root": target}
    trees: list[dict] = []

    for path in paths:
        logger.debug(f"Scanning: {path}")
        if progress_cb:
            tree, stats = scan(path, on_progress=progress_cb, max_depth=args.max_depth)
        else:
            tree, stats = scan(path, max_depth=args.max_depth)
        trees.append(tree)
        combined_stats["files"] += stats["files"]
        combined_stats["dirs"] += stats["dirs"]
        combined_stats["skipped"] += stats["skipped"]
        combined_stats["elapsed_s"] += stats["elapsed_s"]

        flat = build_flat(
            tree,
            max_nodes=int(args.max_nodes),
            min_size=args.min_size,
            categories=args.category or None,
            exclude_dirs=args.exclude or None,
        )
        all_flat.extend(flat)

    # Apply regex filter to flat list
    if filter_re:
        all_flat = [n for n in all_flat if n.get("parent") is None or filter_re.search(n.get("name", ""))]

    # Sort if needed
    if args.sort == "name":
        all_flat.sort(key=lambda n: n.get("name", "").lower())
    else:
        all_flat.sort(key=lambda n: n.get("size", 0), reverse=True)
    if args.reverse:
        all_flat.reverse()

    # Output
    if args.format == "json":
        total_bytes = sum(t.get("size", 0) for t in trees)
        combined_stats["total_bytes"] = total_bytes
        if not args.dry_run and len(trees) == 1:
            render_html(trees[0], all_flat, html_out, csv_out, skip_html=args.no_html)
        combined_stats["total_bytes"] = total_bytes
        _output_json(trees[0], combined_stats, all_flat, target, html_out, csv_out, dry_run=args.dry_run)
    elif args.format == "csv":
        if not args.dry_run and len(trees) == 1:
            render_html(trees[0], all_flat, html_out, csv_out, skip_html=args.no_html)
        _output_csv(all_flat)
    elif args.format == "tsv":
        if not args.dry_run and len(trees) == 1:
            render_html(trees[0], all_flat, html_out, csv_out, skip_html=args.no_html)
        _output_tsv(all_flat)
    elif args.format == "html":
        if not args.dry_run and len(trees) == 1:
            render_html(trees[0], all_flat, html_out, csv_out, skip_html=args.no_html)
        _output_html_table(all_flat)
    else:
        # Text mode
        if progress_cb:
            sys.stderr.write("\r" + " " * 100 + "\r")
            sys.stderr.flush()

        if not args.dry_run and len(trees) == 1:
            render_html(trees[0], all_flat, html_out, csv_out, skip_html=args.no_html)

        combined_stats["total_bytes"] = sum(t.get("size", 0) for t in trees)
        combined_stats["filter"] = args.filter
        _output_text(combined_stats, target, html_out, csv_out, C)

        # Category summary in text mode
        all_nodes = [n for n in all_flat if n.get("parent") is not None]
        if all_nodes:
            cats: dict[str, int] = {}
            for n in all_nodes:
                c = n.get("category", "unknown")
                cats[c] = cats.get(c, 0) + 1
            print(f"\n{C.BOLD}Categories:{C.RESET}")
            for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
                print(f"  {C.CYAN}{cat:>10}{C.RESET}: {cnt:>6} nodes")

        # Show top N files in text mode
        if args.top > 0 and all_flat:
            files_only = [n for n in all_flat if n.get("category") != "folder" and n.get("parent") is not None]
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
                added, removed, changed = _compare_reports(all_flat, args.compare)
            except FileNotFoundError as exc:
                logger.error(f"Compare error: {exc}")
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

    logger.debug("diskstat completed successfully")
