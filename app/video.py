"""Serve uploaded job videos back to the product and embed pages.

Security: the route never accepts a caller-supplied path. It only
serves the stored_path recorded for a job, and only when that path
resolves inside the app's upload directory — anything else (empty
path, missing file, a path escaping the directory, even via a
symlink) is treated as "no video". Visibility matches the product
page: anyone who knows the job_id can watch; no new auth model.
"""
import os
from pathlib import Path


def resolve_job_video_path(job: dict, upload_dir: str) -> str | None:
    """Return the on-disk video for a job, or None when there is none.

    stored_path is interpreted exactly as recorded: absolute paths
    as-is, relative paths against the process working directory
    (which is how the upload route wrote them). The resolved path
    must land inside upload_dir, or the job is treated as videoless.
    """
    stored = (job.get("stored_path") or "").strip()
    if not stored:
        return None
    base = Path(os.path.realpath(upload_dir))
    if os.path.isabs(stored):
        candidate = Path(os.path.realpath(stored))
    else:
        candidate = Path(os.path.realpath(os.path.join(os.getcwd(), stored)))
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return str(candidate)


def job_has_video(job: dict, upload_dir: str) -> bool:
    """True when the job has a servable video file."""
    return resolve_job_video_path(job, upload_dir) is not None
