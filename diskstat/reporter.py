"""Output formatting: CSV, TSV, JSON, text, HTML, and report comparison."""

from __future__ import annotations

import csv
import json
import os
from typing import Any, IO

from .scanner import format_bytes


def _write_csv(flat: list[dict], csv_path: str) -> None:
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


def _write_csv_to_stream(flat: list[dict], stream: IO[str]) -> None:
    """Write flat node list as CSV to a stream."""
    w = csv.writer(stream)
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


def _write_tsv_to_stream(flat: list[dict], stream: IO[str]) -> None:
    """Write flat node list as TSV to a stream."""
    w = csv.writer(stream, delimiter="\t")
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


def _write_html_to_stream(flat: list[dict], stream: IO[str]) -> None:
    """Write flat node list as a minimal HTML table to a stream."""
    stream.write("<table>\n")
    stream.write("<tr><th>name</th><th>path</th><th>size_bytes</th><th>size_human</th><th>category</th><th>parent</th></tr>\n")
    for row in flat:
        name = _html_escape(row.get("name", ""))
        path = _html_escape(row.get("path", ""))
        stream.write(
            f"<tr><td>{name}</td><td>{path}</td>"
            f"<td>{row.get('size', 0)}</td>"
            f"<td>{format_bytes(row.get('size', 0))}</td>"
            f"<td>{row.get('category', 'unknown')}</td>"
            f"<td>{_html_escape(str(row.get('parent', '')))}</td></tr>\n"
        )
    stream.write("</table>\n")


def _html_escape(s: str) -> str:
    """Basic HTML escape."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _compare_reports(
    current_flat: list[dict],
    baseline_path: str,
) -> tuple[dict[str, int], dict[str, int], dict[str, tuple[int, int]]]:
    """Compare current scan against a baseline CSV. Returns (added, removed, changed)."""
    if not os.path.isfile(baseline_path):
        raise FileNotFoundError(f"Baseline not found: {baseline_path}")

    current = {n["path"]: n["size"] for n in current_flat if n.get("parent") is not None and n.get("path")}

    baseline: dict[str, int] = {}
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
    changed: dict[str, tuple[int, int]] = {}
    for k in current:
        if k in baseline and current[k] != baseline[k]:
            changed[k] = (baseline[k], current[k])

    return added, removed, changed


def _output_json(
    tree: dict,
    stats: dict,
    flat: list[dict],
    target: str,
    html_out: str,
    csv_out: str,
    dry_run: bool = False,
) -> None:
    """Output results as JSON."""
    total = tree.get("size", 0)
    result: dict[str, Any] = {
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


def _output_text(
    stats: dict,
    target: str,
    html_out: str,
    csv_out: str,
    C: object,
) -> None:
    """Output results as colored text."""
    total = stats.get("total_bytes", 0)
    root = stats.get("root", target)
    done_mark = "OK" if C.GREEN == "" else "\u2713"
    print(f"{C.BOLD}DiskStat{C.RESET} \u2014 {C.CYAN}{root}{C.RESET}")
    print(f"{C.GREEN}{done_mark}{C.RESET} Done in {C.BOLD}{stats['elapsed_s']}s{C.RESET}")
    print(f"  {stats['dirs']} dirs  {stats['files']} files  "
          f"{stats['skipped']} skipped  {C.BOLD}{format_bytes(total)}{C.RESET} total")
    print(f"  {C.CYAN}HTML{C.RESET} : {html_out}")
    print(f"  {C.CYAN}CSV {C.RESET} : {csv_out}")


def _output_csv(flat: list[dict]) -> None:
    """Output flat list as CSV to stdout."""
    _write_csv_to_stream(flat, sys.stdout)


def _output_tsv(flat: list[dict]) -> None:
    """Output flat list as TSV to stdout."""
    _write_tsv_to_stream(flat, sys.stdout)


def _output_html_table(flat: list[dict]) -> None:
    """Output flat list as HTML table to stdout."""
    _write_html_to_stream(flat, sys.stdout)


import sys  # noqa: E402  -- needed for stream output
