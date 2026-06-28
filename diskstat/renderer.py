"""HTML rendering for diskstat reports."""

from __future__ import annotations

import html as html_mod
import json
import os
import subprocess
import webbrowser
from pathlib import Path

from .config import EXT_COLORS
from .scanner import format_bytes


def esc(value: str) -> str:
    """HTML-escape a string (alias for html.escape)."""
    return html_mod.escape(value)


def _find_template() -> Path:
    """Locate template.html -- checks submodule then project root."""
    here = Path(__file__).parent
    _candidates = [
        here / "template.html",
        here.parent / "template.html",
    ]
    for p in _candidates:
        if p.exists():
            return p
    raise FileNotFoundError(f"template.html not found. Searched: {_candidates}")


def _render_template(
    template_path: Path,
    root_name: str,
    stats_line: str,
    flat: list[dict],
    colors: dict[str, str],
) -> str:
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


def render_html(
    tree_data: dict,
    flat: list[dict],
    output_html: str,
    csv_path: str,
    skip_html: bool = False,
) -> None:
    """Render the WinDirStat-like HTML report from a template file."""
    from .reporter import _write_csv

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


def _open_report(html_out: str) -> None:
    """Open HTML report in browser. Handles WSL->Windows path conversion."""
    # WSL: convert /mnt/X/... paths to X:\\... for cmd.exe
    html_win = html_out
    for mnt_letter in "cdefghijklmnopqrstuvwxyz":
        prefix = f"/mnt/{mnt_letter}/"
        if html_out.startswith(prefix):
            html_win = html_out.replace(prefix, f"{mnt_letter.upper()}:\\").replace("/", "\\")
            break
    else:
        # Not under /mnt/ -- use file:// URL
        html_win = "file://" + html_out

    # Try WSL path to Windows cmd.exe (any drive letter)
    cmd_path = None
    for letter in "cdefghijklmnopqrstuvwxyz":
        candidate = f"/mnt/{letter}/Windows/System32/cmd.exe"
        if os.path.exists(candidate):
            cmd_path = candidate
            break

    if cmd_path:
        subprocess.run([cmd_path, "/c", "start", "", html_win], shell=False)
    else:
        webbrowser.open(html_win)
