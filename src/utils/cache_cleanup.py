import time
from pathlib import Path


def get_stale_files(
    folder_path: Path, max_age_seconds: float, now: float | None = None
) -> list[Path]:
    cutoff = (time.time() if now is None else now) - max_age_seconds
    stale_files = []
    for path in folder_path.glob("*"):
        try:
            if path.is_file() and path.stat().st_mtime <= cutoff:
                stale_files.append(path)
        except OSError:
            continue
    return stale_files
