"""Load initial-data/ into the database (specs/12-initial-data.md §1–2)."""

import hashlib
from pathlib import Path

from django.conf import settings
from django.core.files import File

from .models import Document
from .parsers import detect_format
from .pipeline import run_pipeline


def is_ignored(path: Path) -> bool:
    name = path.name
    return (
        name.endswith(":Zone.Identifier")
        or name.startswith((".", "~$"))
        or name in ("Thumbs.db", "desktop.ini")
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


COMPANY_SEED_BLOCKED_MESSAGE = (
    "개인 버전에서는 기존 가상 회사자료(initial-data/company) 적재를 사용하지 않습니다. "
    "회사 자료 화면에서 실제 필텍 자료를 직접 등록하세요."
)


def load_company(*, mode: str = "skip", report=lambda p, m="": None) -> dict:
    """Create/refresh company documents and apply them to company tables."""
    from apps.company.mapping import fill_company_from_documents, link_delivery_products

    root = Path(settings.INITIAL_DATA_DIR) / "company"
    if not root.is_dir():
        raise FileNotFoundError(f"initial-data/company 폴더가 없습니다: {root}")

    files = sorted(p for p in root.rglob("*") if p.is_file() and not is_ignored(p))
    summary = {"created": 0, "updated": 0, "skipped": 0, "failed": [], "documents": []}
    # Datasheets first so test reports and delivery rows can link to products.
    order = {"datasheets": 0, "test_reports": 1, "certificates": 2, "records": 3}
    files.sort(key=lambda p: (order.get(p.parent.name, 9), p.name))

    for index, path in enumerate(files, start=1):
        report(int(index / len(files) * 90), f"{path.name} 처리 중")
        file_format = detect_format(path.name)
        if file_format is None:
            summary["skipped"] += 1
            continue
        sha = file_sha256(path)
        document = Document.objects.filter(sha256=sha, owner_type="COMPANY").first()
        if document and mode == "skip":
            summary["skipped"] += 1
            continue
        if document is None:
            document = Document(
                owner_type="COMPANY",
                original_filename=path.name,
                file_format=file_format,
                file_size=path.stat().st_size,
                sha256=sha,
            )
            with path.open("rb") as handle:
                document.file.save(path.name, File(handle), save=True)
            summary["created"] += 1
        else:
            summary["updated"] += 1

        relative = str(path.relative_to(root.parent))
        try:
            result = run_pipeline(document, path_hint=relative, apply=True)
        except Exception as exc:  # keep loading other files; report per-file failure
            summary["failed"].append({"file": relative, "error": str(exc)})
            continue
        if result["status"] not in (Document.Status.REVIEWED, Document.Status.EXTRACTED):
            summary["failed"].append({"file": relative, "error": document.error_message})
        summary["documents"].append(document.pk)

    link_delivery_products()
    fill_company_from_documents(Document.objects.filter(owner_type="COMPANY"))
    report(100, "완료")
    return summary
