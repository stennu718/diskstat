"""Configuration, constants, and config-file loading for diskstat."""

from __future__ import annotations

import json
import os
from typing import Any


# ── Extension-category colour map (used by renderer) ──────────────────────
EXT_COLORS: dict[str, str] = {
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

# ── Extension → category mapping ──────────────────────────────────────────
EXT_MAP: dict[str, set[str]] = {
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

# ── Scan depth / node limits ─────────────────────────────────────────────
_MAX_SCAN_DEPTH: int = 256       # prevent runaway recursion from deep nesting
_DEFAULT_MAX_NODES: int = 5000   # default max nodes in visualization


def _load_config(path: str) -> dict[str, Any]:
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
