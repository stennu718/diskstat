"""XDG-compliant configuration discovery and schema validation."""

from __future__ import annotations

import json
import os
from pathlib import Path
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

# Scan depth / node limits
_MAX_SCAN_DEPTH: int = 256       # prevent runaway recursion from deep nesting
_DEFAULT_MAX_NODES: int = 5000   # default max nodes in visualization

# Default config values
_DEFAULTS: dict[str, Any] = {
    "exclude": [],
    "category": [],
    "max_nodes": 5000,
    "min_size": 0,
    "max_depth": 256,
    "sort": "size",
    "top": 0,
    "filter": None,
    "format": "text",
    "no_color": False,
    "progress": True,
    "no_html": False,
}

# Valid values for validation
_VALID_SORT = {"size", "name"}
_VALID_FORMAT = {"text", "json", "csv", "tsv", "html"}
_VALID_CATEGORIES = {
    "folder", "unknown", "zip", "image", "video", "audio",
    "doc", "code", "exe", "font", "data", "system",
}


def _find_config_path() -> Path | None:
    """Find config file using XDG Base Directory Spec.

    Search order:
    1. $DISKSTAT_CONFIG_PATH (explicit env override)
    2. $XDG_CONFIG_HOME/diskstat/config.yaml
    3. ~/.config/diskstat/config.yaml
    """
    # Explicit override
    env_path = os.environ.get("DISKSTAT_CONFIG_PATH")
    if env_path:
        p = Path(env_path)
        return p if p.exists() else None

    # XDG_CONFIG_HOME
    xdg_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_home:
        p = Path(xdg_home) / "diskstat" / "config.yaml"
        if p.exists():
            return p
        # Also check .json variant
        p_json = p.with_suffix(".json")
        if p_json.exists():
            return p_json

    # Default: ~/.config/diskstat/
    p = Path.home() / ".config" / "diskstat" / "config.yaml"
    if p.exists():
        return p
    p_json = p.with_suffix(".json")
    if p_json.exists():
        return p_json

    return None


def _validate_config(config: dict[str, Any]) -> list[str]:
    """Validate config dict. Returns list of error messages."""
    errors: list[str] = []

    for key in config:
        if key not in _DEFAULTS:
            errors.append(f"Unknown config key: {key}")

    if "sort" in config and config["sort"] not in _VALID_SORT:
        errors.append(f"Invalid sort: {config['sort']!r} (valid: {_VALID_SORT})")

    if "format" in config and config["format"] not in _VALID_FORMAT:
        errors.append(f"Invalid format: {config['format']!r} (valid: {_VALID_FORMAT})")

    if "max_nodes" in config:
        v = config["max_nodes"]
        if not isinstance(v, int) or v < 1:
            errors.append(f"Invalid max_nodes: {v!r} (must be positive int)")

    if "min_size" in config:
        v = config["min_size"]
        if not isinstance(v, (int, float)) or v < 0:
            errors.append(f"Invalid min_size: {v!r} (must be non-negative)")

    if "max_depth" in config:
        v = config["max_depth"]
        if not isinstance(v, int) or v < 0:
            errors.append(f"Invalid max_depth: {v!r} (must be non-negative int)")

    if "category" in config:
        cats = config["category"]
        if isinstance(cats, list):
            for c in cats:
                if c not in _VALID_CATEGORIES:
                    errors.append(f"Invalid category: {c!r}")

    if "exclude" in config:
        excl = config["exclude"]
        if not isinstance(excl, list):
            errors.append(f"Invalid exclude: must be a list of strings")

    return errors


def load_config(path: str | None = None) -> dict[str, Any]:
    """Load and validate config. Returns merged config dict.

    Args:
        path: explicit path to config file. If None, uses XDG discovery.

    Returns:
        Merged config dict (defaults + file values).
    """
    config_path: Path | None = None

    if path:
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
    else:
        config_path = _find_config_path()

    config: dict[str, Any] = dict(_DEFAULTS)

    if config_path and config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            if config_path.suffix in (".yaml", ".yml"):
                try:
                    import yaml
                    raw = yaml.safe_load(f) or {}
                except ImportError:
                    raise ImportError(
                        "PyYAML required for .yaml config: pip install pyyaml"
                    )
            else:
                raw = json.load(f)
            if isinstance(raw, dict):
                config.update(raw)

    errors = _validate_config(config)
    if errors:
        raise ValueError(f"Config validation failed:\n  - " + "\n  - ".join(errors))

    return config


def get_default_config() -> dict[str, Any]:
    """Return a copy of the default config."""
    return dict(_DEFAULTS)
