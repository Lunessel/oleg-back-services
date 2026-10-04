from pathlib import Path
from uuid import uuid4


def is_local(image: str) -> bool:
    return not image.startswith(("http://", "https://"))


def new_image_name() -> str:
    return f"services/{uuid4().hex}.jpg"


def image_path(media_dir: Path, image: str) -> Path:
    return media_dir / image


def delete_image(media_dir: Path, image: str) -> None:
    if is_local(image):
        image_path(media_dir, image).unlink(missing_ok=True)


def public_url(base_url: str, image: str) -> str:
    if not is_local(image):
        return image
    return f"{base_url.rstrip('/')}/media/{image}"
