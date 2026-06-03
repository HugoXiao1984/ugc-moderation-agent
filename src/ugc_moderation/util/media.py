"""Media helpers: resize, phash, S3 URI parsing."""
from __future__ import annotations

import base64
import io
from urllib.parse import urlparse

from PIL import Image

try:
    import imagehash
except ImportError:
    imagehash = None


def parse_s3_uri(uri: str) -> tuple[str, str]:
    """s3://bucket/key -> (bucket, key)."""
    p = urlparse(uri)
    if p.scheme != "s3":
        raise ValueError(f"Not an s3 URI: {uri}")
    return p.netloc, p.path.lstrip("/")


def resize_for_nova(image_bytes: bytes, max_side: int = 1568) -> bytes:
    """Return JPEG bytes suitable for Nova Pro.

    Always re-encodes to JPEG so the Converse API's declared `format: "jpeg"`
    matches the real MIME type (Nova rejects PNG bytes with a jpeg declaration).
    """
    img = Image.open(io.BytesIO(image_bytes))
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def image_phash(image_bytes: bytes) -> str:
    """Perceptual hash (falls back to size-only signature if imagehash missing)."""
    if imagehash is None:
        img = Image.open(io.BytesIO(image_bytes))
        return f"noph-{img.size[0]}x{img.size[1]}-{len(image_bytes)}"
    return str(imagehash.phash(Image.open(io.BytesIO(image_bytes))))


def image_to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode()
