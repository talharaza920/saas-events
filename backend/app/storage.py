"""Image storage for admin uploads — one abstraction, two backends.

  • LOCAL DEV: write the file under `backend/uploads/<wedding_slug>/<uuid>.<ext>`
    and return a URL served by the FastAPI `/media` static mount (see main.py).
  • PRODUCTION: upload to a public Supabase Storage bucket and return its public
    URL. Selected automatically when Supabase URL + service key are configured
    (`settings.use_supabase_storage`).

Either way the caller (the admin upload endpoint) gets back a plain URL string,
which is stored verbatim as a story beat's `image`. The invite renders it with
`next/image` — see frontend/next.config.ts `remotePatterns`. Multi-tenant:
uploads are namespaced by wedding slug.
"""
from __future__ import annotations

import io
import logging
import uuid
from pathlib import Path

from app.config import Settings

# backend/uploads (repo-relative, gitignored). Served at /media in dev.
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"

# Accepted image types → canonical extension.
ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
}
_PIL_FORMAT = {"png": "PNG", "jpg": "JPEG", "webp": "WEBP"}

# Accept generous originals (phone photos / comic exports run large) — we shrink
# them server-side before storing, so the cap is just a sanity guard, not the
# size that lands in storage.
MAX_BYTES = 15 * 1024 * 1024  # 15 MB cap on the UPLOADED file.
MAX_DIM = 1600  # longest edge after compression (matches the frontend optimizer).

# --- AI wizard input media (app/ai/media.py) ---------------------------------
# Raw submissions for the AI wizard (voice notes, venue PDFs, photos). They
# live under their own `ai-inputs/<wedding>` namespace so the storage metering
# (measure_wedding_media / reconcile cron) never counts them — they are
# TRANSIENT PII, deleted when their job terminates or the reap cron sweeps
# orphans, and never rendered on any page.
AI_INPUT_NAMESPACE = "ai-inputs"

# mime → (input kind, canonical extension). Audio formats are the set Gemini
# documents (WAV/MP3/AAC/OGG/FLAC; m4a is AAC-in-mp4).
ALLOWED_AI_MEDIA_TYPES: dict[str, tuple[str, str]] = {
    "image/png": ("image", "png"),
    "image/jpeg": ("image", "jpg"),
    "image/jpg": ("image", "jpg"),
    "image/webp": ("image", "webp"),
    "application/pdf": ("pdf", "pdf"),
    "audio/mpeg": ("audio", "mp3"),
    "audio/mp3": ("audio", "mp3"),
    "audio/wav": ("audio", "wav"),
    "audio/x-wav": ("audio", "wav"),
    "audio/ogg": ("audio", "ogg"),
    "audio/flac": ("audio", "flac"),
    "audio/aac": ("audio", "aac"),
    "audio/mp4": ("audio", "m4a"),
    "audio/x-m4a": ("audio", "m4a"),
    # Sheets (8.5c). Read in CODE (app/ai/sheets.py), never sent to a provider —
    # they're here so a couple can hand the assistant the spreadsheet that isn't
    # our import template, not because a model is going to look at it.
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ("sheet", "xlsx"),
    "text/csv": ("sheet", "csv"),
    "application/csv": ("sheet", "csv"),
}
# Gemini's inline-media request cap is 20 MB INCLUDING base64 inflation (~4/3),
# so 10 MB of raw file leaves comfortable headroom for the prompt around it.
MAX_AI_MEDIA_BYTES = 10 * 1024 * 1024


class UploadError(Exception):
    """Raised for an invalid upload (bad type / too large). The router maps it to a 4xx."""


def _safe_slug(wedding_slug: str) -> str:
    """A filesystem/URL-safe namespace segment from the wedding slug."""
    return "".join(c for c in wedding_slug if c.isalnum() or c in ("-", "_")) or "wedding"


def validate(content_type: str | None, size: int) -> str:
    """Validate type + size; return the canonical file extension or raise."""
    ext = ALLOWED_CONTENT_TYPES.get((content_type or "").lower())
    if ext is None:
        raise UploadError("Unsupported image type (use PNG, JPG or WebP)")
    if size > MAX_BYTES:
        raise UploadError("Image is too large (max 15 MB)")
    if size == 0:
        raise UploadError("Empty file")
    return ext


def compress_image(data: bytes, ext: str) -> bytes:
    """Downscale to <= MAX_DIM on the longest edge and re-encode, so even a large
    original lands small in storage. Best-effort: if the bytes aren't a decodable
    image (or Pillow is unavailable), return them unchanged — `validate` already
    bounded the size."""
    try:
        from PIL import Image, ImageOps

        fmt = _PIL_FORMAT.get(ext, "PNG")
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im)  # honour phone-photo rotation
            if fmt == "JPEG" and im.mode in ("RGBA", "P", "LA"):
                im = im.convert("RGB")  # JPEG has no alpha
            im.thumbnail((MAX_DIM, MAX_DIM))  # no-op if already smaller; keeps ratio
            buf = io.BytesIO()
            save_kwargs: dict = {"optimize": True}
            if fmt in ("JPEG", "WEBP"):
                save_kwargs["quality"] = 82
            im.save(buf, format=fmt, **save_kwargs)
            out = buf.getvalue()
        # Only keep the re-encode if it actually helped (PNG optimize can grow tiny
        # images); otherwise store the original.
        return out if out and len(out) <= len(data) else data
    except Exception:
        return data


def prepare_image(data: bytes, content_type: str | None) -> tuple[bytes, str]:
    """Validate + compress an upload; returns (bytes_to_store, ext). Split from
    `store_image` so the caller can gate on the EXACT stored size (storage
    entitlement) before anything is persisted."""
    ext = validate(content_type, len(data))
    return compress_image(data, ext), ext


def store_image(
    settings: Settings, wedding_slug: str, data: bytes, ext: str, content_type: str
) -> str:
    """Persist already-prepared image bytes; return the public URL."""
    namespace = _safe_slug(wedding_slug)
    filename = f"{uuid.uuid4().hex}.{ext}"
    if settings.use_supabase_storage:
        return _save_supabase(settings, namespace, filename, data, content_type)
    return _save_local(settings, namespace, filename, data)


def save_image(settings: Settings, wedding_slug: str, data: bytes, content_type: str | None) -> str:
    """Validate, compress, then persist an uploaded image; return its public URL."""
    data, ext = prepare_image(data, content_type)
    return store_image(settings, wedding_slug, data, ext, content_type or "image/png")


# --- AI wizard input media ----------------------------------------------------
def validate_ai_media(content_type: str | None, size: int) -> tuple[str, str]:
    """Validate an AI-input upload; return (input kind, extension) or raise."""
    entry = ALLOWED_AI_MEDIA_TYPES.get((content_type or "").lower())
    if entry is None:
        raise UploadError(
            "Unsupported file type — use a spreadsheet (XLSX/CSV), an image "
            "(PNG/JPG/WebP), a PDF, or an audio file (MP3/WAV/M4A/OGG/FLAC/AAC)"
        )
    if size > MAX_AI_MEDIA_BYTES:
        raise UploadError("File is too large (max 10 MB)")
    if size == 0:
        raise UploadError("Empty file")
    return entry


def store_ai_input(
    settings: Settings, wedding_slug: str, data: bytes, ext: str, content_type: str
) -> str:
    """Persist one raw AI submission under the transient ai-inputs namespace;
    return its URL (stored on the AiInput row, deleted with it)."""
    namespace = f"{AI_INPUT_NAMESPACE}/{_safe_slug(wedding_slug)}"
    filename = f"{uuid.uuid4().hex}.{ext}"
    if settings.use_supabase_storage:
        return _save_supabase(settings, namespace, filename, data, content_type)
    return _save_local(settings, namespace, filename, data)


def _object_path_from_url(settings: Settings, url: str) -> str | None:
    """The bucket object path (or UPLOAD_DIR-relative path) a stored URL points
    at, or None when the URL isn't one of ours — callers must treat None as
    'not our object, do nothing' (never fetch/delete an arbitrary URL)."""
    if settings.use_supabase_storage:
        prefix = (
            f"{settings.supabase_url.rstrip('/')}/storage/v1/object/public/"
            f"{settings.supabase_storage_bucket}/"
        )
        return url[len(prefix):] if url.startswith(prefix) else None
    prefix = f"{settings.media_base_url.rstrip('/')}/media/"
    if not url.startswith(prefix):
        return None
    rel = url[len(prefix):]
    # Belt-and-braces traversal guard: the path we mint is always uuid-named
    # under a slug-safe namespace, so anything stranger is not ours.
    if ".." in rel or rel.startswith("/") or "\\" in rel:
        return None
    return rel


def load_media_bytes(settings: Settings, url: str) -> bytes:
    """Fetch the bytes behind a URL this module stored (AI transcription needs
    the raw file back). Raises UploadError when the URL isn't ours or the
    fetch fails."""
    path = _object_path_from_url(settings, url)
    if path is None:
        raise UploadError("Stored file URL is not recognised")
    if settings.use_supabase_storage:
        import httpx

        base = settings.supabase_url.rstrip("/")
        resp = httpx.get(
            # The authenticated endpoint, not /public/ — works even if the
            # bucket is later made private.
            f"{base}/storage/v1/object/{settings.supabase_storage_bucket}/{path}",
            headers={
                "Authorization": f"Bearer {settings.supabase_service_key}",
                "apikey": settings.supabase_service_key,
            },
            timeout=30.0,
        )
        if resp.status_code != 200:
            raise UploadError(f"Stored file fetch failed ({resp.status_code})")
        return resp.content
    file = (UPLOAD_DIR / path).resolve()
    if not str(file).startswith(str(UPLOAD_DIR.resolve())) or not file.is_file():
        raise UploadError("Stored file is missing")
    return file.read_bytes()


def delete_media_object(settings: Settings, url: str) -> None:
    """Best-effort delete of ONE stored object by its URL (AI input sweep /
    unused generated images). Never raises — cleanup must not block the state
    change that triggered it."""
    try:
        path = _object_path_from_url(settings, url)
        if path is None:
            return
        if settings.use_supabase_storage:
            import httpx

            base = settings.supabase_url.rstrip("/")
            httpx.request(
                "DELETE",
                f"{base}/storage/v1/object/{settings.supabase_storage_bucket}",
                json={"prefixes": [path]},
                headers={
                    "Authorization": f"Bearer {settings.supabase_service_key}",
                    "apikey": settings.supabase_service_key,
                },
                timeout=30.0,
            ).raise_for_status()
        else:
            file = (UPLOAD_DIR / path).resolve()
            if str(file).startswith(str(UPLOAD_DIR.resolve())) and file.is_file():
                file.unlink()
    except Exception as exc:  # noqa: BLE001 — deliberately swallowed, see docstring
        logging.getLogger("app.storage").warning("media object delete failed: %s", exc)


def measure_wedding_media(settings: Settings, wedding_slug: str) -> int | None:
    """Total bytes actually in storage under a wedding's namespace, or None when
    it can't be measured (provider error) — callers must treat None as "leave
    the counter alone", never as zero."""
    namespace = _safe_slug(wedding_slug)
    try:
        if settings.use_supabase_storage:
            return _measure_supabase_prefix(settings, namespace)
        folder = UPLOAD_DIR / namespace
        if not folder.is_dir():
            return 0
        return sum(f.stat().st_size for f in folder.iterdir() if f.is_file())
    except Exception as exc:  # noqa: BLE001 — measurement is advisory
        logging.getLogger("app.storage").warning("media measure failed for %s: %s", namespace, exc)
        return None


def _measure_supabase_prefix(settings: Settings, namespace: str) -> int:
    """Sum object sizes under `namespace/` via the Storage list API."""
    import httpx

    bucket = settings.supabase_storage_bucket
    base = settings.supabase_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "apikey": settings.supabase_service_key,
    }
    resp = httpx.post(
        f"{base}/storage/v1/object/list/{bucket}",
        json={"prefix": namespace, "limit": 1000},
        headers=headers,
        timeout=30.0,
    )
    resp.raise_for_status()
    return sum(
        int((item.get("metadata") or {}).get("size") or 0)
        for item in resp.json()
        if item.get("name")
    )


def _save_local(settings: Settings, namespace: str, filename: str, data: bytes) -> str:
    dest_dir = UPLOAD_DIR / namespace
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / filename).write_bytes(data)
    base = settings.media_base_url.rstrip("/")
    return f"{base}/media/{namespace}/{filename}"


def delete_wedding_media(settings: Settings, wedding_slug: str) -> None:
    """Best-effort removal of every upload under a wedding's namespace — called by
    the archived-wedding purge. Never raises: media cleanup must not block the DB
    purge (an orphaned public image is a cost/PII nit, a failed purge is worse)."""
    namespace = _safe_slug(wedding_slug)
    # The wedding's rendered media AND its transient AI-input namespace.
    for prefix in (namespace, f"{AI_INPUT_NAMESPACE}/{namespace}"):
        try:
            if settings.use_supabase_storage:
                _delete_supabase_prefix(settings, prefix)
            else:
                import shutil

                shutil.rmtree(UPLOAD_DIR / prefix, ignore_errors=True)
        except Exception as exc:  # noqa: BLE001 — deliberately swallowed, see docstring
            logging.getLogger("app.storage").warning("media purge failed for %s: %s", prefix, exc)


def _delete_supabase_prefix(settings: Settings, namespace: str) -> None:
    """List then bulk-delete every object under `namespace/` in the bucket (the
    Storage API deletes exact object paths, not folders)."""
    import httpx

    bucket = settings.supabase_storage_bucket
    base = settings.supabase_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "apikey": settings.supabase_service_key,
    }
    resp = httpx.post(
        f"{base}/storage/v1/object/list/{bucket}",
        json={"prefix": namespace, "limit": 1000},
        headers=headers,
        timeout=30.0,
    )
    resp.raise_for_status()
    names = [item["name"] for item in resp.json() if item.get("name")]
    if not names:
        return
    httpx.request(
        "DELETE",
        f"{base}/storage/v1/object/{bucket}",
        json={"prefixes": [f"{namespace}/{n}" for n in names]},
        headers=headers,
        timeout=30.0,
    ).raise_for_status()


def _save_supabase(
    settings: Settings, namespace: str, filename: str, data: bytes, content_type: str
) -> str:
    """Upload to a public Supabase Storage bucket via its REST API (lazy import so
    local dev never needs the SDK). Returns the public URL."""
    import httpx  # already a FastAPI/Supabase dependency

    bucket = settings.supabase_storage_bucket
    object_path = f"{namespace}/{filename}"
    base = settings.supabase_url.rstrip("/")
    upload_url = f"{base}/storage/v1/object/{bucket}/{object_path}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "apikey": settings.supabase_service_key,
        "Content-Type": content_type,
        "x-upsert": "true",
    }
    resp = httpx.post(upload_url, content=data, headers=headers, timeout=30.0)
    if resp.status_code not in (200, 201):
        raise UploadError(f"Storage upload failed ({resp.status_code})")
    return f"{base}/storage/v1/object/public/{bucket}/{object_path}"
