"""DiskStat — Disk usage analyzer (WinDirStat-like) with interactive treemap + CSV reports."""

from .cli import main, _parse_args, _make_colors, _supports_color
from .scanner import _resolve_path, format_bytes, ext_category, scan, build_flat
from .renderer import render_html, _find_template, _render_template, _open_report
from .reporter import _write_csv, _compare_reports, _output_json, _output_text
from .config import EXT_COLORS, EXT_MAP, _MAX_SCAN_DEPTH, _load_config

__all__ = [
    "main",
    "_parse_args",
    "_resolve_path",
    "format_bytes",
    "ext_category",
    "scan",
    "build_flat",
    "render_html",
    "_find_template",
    "_render_template",
    "_open_report",
    "_write_csv",
    "_compare_reports",
    "_output_json",
    "_output_text",
    "_make_colors",
    "_supports_color",
    "EXT_COLORS",
    "EXT_MAP",
    "_MAX_SCAN_DEPTH",
    "_load_config",
]
