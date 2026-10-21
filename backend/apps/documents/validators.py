"""Upload validation: extension whitelist, size limit and content sniffing (specs/01 §7)."""

from pathlib import Path

from apps.core.app_settings import get_setting

from .loader import is_ignored
from .parsers import detect_format

ALLOWED_FORMATS = {
    "COMPANY": {"TXT", "DOCX", "DOC", "HWP", "HWPX", "PDF"},
    "BID": {"TXT", "DOCX", "DOC", "HWP", "HWPX", "PDF", "XLS", "XLSX"},
}

_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_ZIP = b"PK\x03\x04"
MAGIC = {
    "PDF": [b"%PDF"],
    "HWP": [_OLE],
    "DOC": [_OLE],
    "XLS": [_OLE],
    "DOCX": [_ZIP],
    "HWPX": [_ZIP],
    "XLSX": [_ZIP],
}


class UploadRejected(Exception):
    pass


def validate_upload(uploaded, owner_type: str) -> str:
    """Return the detected file format or raise UploadRejected with a Korean reason."""
    name = uploaded.name or ""
    if is_ignored(Path(name)):
        raise UploadRejected("시스템/숨김 파일은 업로드하지 않습니다.")
    file_format = detect_format(name)
    if file_format is None or file_format not in ALLOWED_FORMATS[owner_type]:
        allowed = ", ".join(sorted(ALLOWED_FORMATS[owner_type]))
        raise UploadRejected(f"지원하지 않는 형식입니다. 허용: {allowed}")
    max_mb = get_setting("upload.max_mb")
    if uploaded.size > max_mb * 1024 * 1024:
        raise UploadRejected(f"파일이 너무 큽니다 (최대 {max_mb}MB).")
    if uploaded.size == 0:
        raise UploadRejected("빈 파일입니다.")

    head = uploaded.read(8)
    uploaded.seek(0)
    if file_format in MAGIC and not any(head.startswith(m) for m in MAGIC[file_format]):
        raise UploadRejected("파일 내용이 확장자와 일치하지 않습니다.")
    if file_format == "TXT" and b"\x00" in uploaded.read(4096):
        uploaded.seek(0)
        raise UploadRejected("텍스트 파일이 아닙니다.")
    uploaded.seek(0)
    return file_format
