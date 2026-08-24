"""Screenshot persistence and cleanup for Pi Dashboard MCP.

Screenshots are written to a host-mounted directory so they survive
container restarts and can be served over HTTP to any MCP client.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_SCREENSHOT_DIR = "/var/lib/pi-dashboard/screenshots"


def _screenshot_dir() -> Path:
    path = Path(os.environ.get("SCREENSHOT_DIR", DEFAULT_SCREENSHOT_DIR))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_filename(name: str) -> str:
    """Reject any filename containing path separators or parent references."""
    if not name or "/" in name or "\\" in name or ".." in name:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9_\-]+\.png", name):
        return ""
    return name


def save_screenshot(base64_data: str) -> dict[str, Any]:
    """Persist a base64 PNG screenshot and return its metadata.

    Args:
        base64_data: Base64-encoded PNG bytes.

    Returns:
        dict with filename, file_path, url_path, size_bytes and saved_at.
    """
    directory = _screenshot_dir()
    timestamp = time.strftime("%Y%m%d%H%M%S")
    short_id = uuid.uuid4().hex[:8]
    filename = f"{timestamp}_{short_id}.png"
    file_path = directory / filename

    image_bytes = base64_data.encode("utf-8") if isinstance(base64_data, str) else base64_data
    if isinstance(image_bytes, bytes):
        import base64

        image_bytes = base64.b64decode(image_bytes)

    file_path.write_bytes(image_bytes)
    logger.info("Saved screenshot: %s (%d bytes)", file_path, len(image_bytes))

    return {
        "filename": filename,
        "file_path": str(file_path),
        "url_path": f"/screenshots/{filename}",
        "size_bytes": len(image_bytes),
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


async def save_screenshot_async(base64_data: str) -> dict[str, Any]:
    """Async wrapper around save_screenshot."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, save_screenshot, base64_data)


def list_screenshots() -> list[dict[str, Any]]:
    """Return metadata for all persisted screenshots, newest first."""
    directory = _screenshot_dir()
    files: list[dict[str, Any]] = []
    for entry in directory.iterdir():
        if not entry.is_file() or entry.suffix.lower() != ".png":
            continue
        stat = entry.stat()
        files.append(
            {
                "filename": entry.name,
                "file_path": str(entry),
                "url_path": f"/screenshots/{entry.name}",
                "size_bytes": stat.st_size,
                "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(stat.st_mtime)),
                "mtime": stat.st_mtime,
            }
        )
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return files


async def list_screenshots_async() -> list[dict[str, Any]]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, list_screenshots)


def cleanup_screenshots(
    max_age_hours: float | None = None,
    keep_count: int | None = None,
) -> dict[str, Any]:
    """Delete old screenshots based on age or retention count.

    Args:
        max_age_hours: Delete files older than this many hours.
        keep_count: Keep only this many newest files, delete the rest.

    Returns:
        dict with deleted list and count.
    """
    directory = _screenshot_dir()
    files = list_screenshots()
    deleted: list[str] = []
    now = time.time()

    if max_age_hours is not None and max_age_hours > 0:
        cutoff = now - max_age_hours * 3600
        for meta in files:
            if meta["mtime"] < cutoff:
                try:
                    (directory / meta["filename"]).unlink()
                    deleted.append(meta["filename"])
                    logger.info("Deleted old screenshot: %s", meta["filename"])
                except OSError as exc:
                    logger.warning("Failed to delete %s: %s", meta["filename"], exc)

    # Re-list after age-based deletion to avoid double-removal logic issues.
    if keep_count is not None and keep_count >= 0:
        remaining = list_screenshots()
        for meta in remaining[keep_count:]:
            try:
                (directory / meta["filename"]).unlink()
                if meta["filename"] not in deleted:
                    deleted.append(meta["filename"])
                logger.info("Deleted excess screenshot: %s", meta["filename"])
            except OSError as exc:
                logger.warning("Failed to delete %s: %s", meta["filename"], exc)

    return {"deleted": deleted, "count": len(deleted)}


async def cleanup_screenshots_async(
    max_age_hours: float | None = None,
    keep_count: int | None = None,
) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, cleanup_screenshots, max_age_hours, keep_count)


def read_screenshot(filename: str) -> bytes | None:
    """Read a persisted screenshot safely.

    Returns None if the filename is unsafe or the file does not exist.
    """
    safe = _safe_filename(filename)
    if not safe:
        return None
    directory = _screenshot_dir()
    file_path = directory / safe
    try:
        return file_path.read_bytes()
    except OSError:
        return None


async def read_screenshot_async(filename: str) -> bytes | None:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, read_screenshot, filename)
