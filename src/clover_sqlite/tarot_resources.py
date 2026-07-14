from pathlib import Path

from src.configs.path_config import tarots_img_path


def resolve_tarot_image_path(image: str) -> str:
    """Resolve legacy tarot image names against the deployed card resources."""
    path = Path(image)
    if not path.is_absolute():
        path = Path(tarots_img_path) / path
    if path.is_file():
        return str(path)
    for suffix in (".jpg", ".png", ".jpeg"):
        candidate = path.with_suffix(suffix)
        if candidate.is_file():
            return str(candidate)
    return str(path)
