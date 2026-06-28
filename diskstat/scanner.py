"""Directory scanning, tree building, and formatting utilities."""

from __future__ import annotations

import os
import time
from typing import Callable, Optional

from .config import EXT_MAP, _MAX_SCAN_DEPTH


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


def ext_category(name: str, is_dir: bool = False) -> str:
    """Return the category for a file based on its extension."""
    if is_dir:
        return "folder"
    ext = os.path.splitext(name)[1].lower()
    for cat, exts in EXT_MAP.items():
        if ext in exts:
            return cat
    return "unknown"


def format_bytes(b) -> str:
    """Format bytes as human-readable string."""
    if b is None:
        return "—"
    if isinstance(b, float):
        if b != b or b == float('inf') or b == float('-inf'):
            return "—"
    if not isinstance(b, (int, float)):
        return "0.0 B"
    if b <= 0:
        return "0.0 B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = int(min(len(units) - 1, (int(b).bit_length() - 1) // 10))
    v = b / (1024 ** i)
    return f"{v:.1f} {units[i]}"


def scan(
    path: str,
    on_progress: Optional[Callable[[str, int, int], None]] = None,
    max_depth: Optional[int] = None,
) -> tuple[dict, dict]:
    """Scan directory tree. Returns (tree, stats).

    Args:
        path: directory to scan
        on_progress: optional callback(directory, files, dirs)
        max_depth: override default max recursion depth
    """
    _depth_limit = max_depth if max_depth is not None else _MAX_SCAN_DEPTH
    try:
        path = _resolve_path(path)
    except (ValueError, OSError):
        return {"name": os.path.basename(path) or path, "path": path, "size": 0, "category": "folder"}, {
            "files": 0, "dirs": 0, "skipped": 1, "elapsed_s": 0, "root": path,
        }
    root_name = os.path.basename(path) or path
    tree: dict = {"name": root_name, "path": path, "size": 0, "category": "folder"}
    t0 = time.time()
    scanned_files = 0
    scanned_dirs = 0
    skipped = 0

    def _walk(directory: str, node: dict, depth: int = 0) -> int:
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
                    child: dict = {
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

    try:
        _walk(path, tree)
    except (OSError, PermissionError):
        pass
    return tree, {
        "files": scanned_files,
        "dirs": scanned_dirs,
        "skipped": skipped,
        "elapsed_s": round(max(0.0, time.time() - t0), 3),
        "root": path,
    }


def build_flat(
    tree: dict,
    max_nodes: int = 5000,
    min_size: int = 0,
    categories: Optional[set] = None,
    exclude_dirs: Optional[set] = None,
) -> list[dict]:
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
    out: list[dict] = [
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

    queue: list[tuple[dict, str]] = []
    children = tree.get("children", [])
    children.sort(key=lambda x: x.get("size", 0), reverse=True)
    for child in children:
        cname = child.get("name", "")
        ccat = child.get("category", "folder" if "children" in child else "unknown")
        if exclude_dirs and cname in exclude_dirs and ccat == "folder":
            continue
        if categories and ccat not in categories and ccat != "folder":
            continue
        queue.append((child, tree.get("name", "ROOT")))

    count = 1
    while queue and count < max_nodes:
        node, parent_name = queue.pop(0)
        count += 1
        cat = node.get("category", "folder" if "children" in node else "unknown")

        if min_size > 0 and cat != "folder" and node.get("size", 0) < min_size:
            count -= 1
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
