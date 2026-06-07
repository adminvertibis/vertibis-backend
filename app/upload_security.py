import os
import re
import uuid
from pathlib import Path

from fastapi import HTTPException, status


ALLOWED_UPLOAD_EXTENSIONS = {
    ".csv",
    ".json",
    ".pdf",
    ".txt",
    ".xls",
    ".xlsx",
    ".zip",
}
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))


def safe_upload_filename(filename: str | None, fallback_prefix: str = "upload") -> str:
    original = Path(str(filename or "")).name
    stem = Path(original).stem or fallback_prefix
    suffix = Path(original).suffix.lower()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-_")[:80] or fallback_prefix
    if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        suffix = ".dat"
    return f"{stem}-{uuid.uuid4().hex[:10]}{suffix}"


def validate_upload_bytes(content: bytes, filename: str | None = None) -> None:
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Uploaded file exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
        )
    suffix = Path(str(filename or "")).suffix.lower()
    if suffix and suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=f"Unsupported file type: {suffix}")
