from __future__ import annotations

from pathlib import Path


def resolve_image_path(raw_path: str | Path, image_root: str | Path) -> Path | None:
    root = Path(image_root).resolve()
    raw = Path(str(raw_path))
    candidates = [raw] if raw.is_absolute() else []
    if not raw.is_absolute() or not candidates[0].is_file():
        candidates.append(root / raw.name)
    for candidate in candidates:
        resolved = candidate.resolve()
        if root in resolved.parents and resolved.is_file():
            return resolved
    return None
