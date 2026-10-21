"""Load initial-data/bid_sample into bids (specs/12-initial-data.md §3)."""

from pathlib import Path

from django.conf import settings

from apps.documents.loader import file_sha256, is_ignored
from apps.documents.parsers import detect_format
from apps.llm.services import is_llm_configured

from .extraction import extract_bid
from .models import BidNotice
from .services import add_attachment

OUTCOME_FOLDERS = {"won": BidNotice.Outcome.WON, "lost": BidNotice.Outcome.LOST}


def bid_folders() -> list[tuple[Path, str]]:
    root = Path(settings.INITIAL_DATA_DIR) / "bid_sample"
    folders = []
    for name, outcome in OUTCOME_FOLDERS.items():
        base = root / name
        if base.is_dir():
            folders += [(p, outcome) for p in sorted(base.iterdir()) if p.is_dir()]
    return folders


def load_bids(*, mode: str = "skip", use_llm: bool = True, report=lambda p, m="": None) -> dict:
    """One BidNotice per folder; every file becomes an attachment. Extraction runs when the
    LLM is configured (otherwise bids stay DRAFT until "추출 실행")."""
    folders = bid_folders()
    summary = {"created": 0, "updated": 0, "skipped": 0, "extracted": 0, "failed": [], "bids": []}
    extract = use_llm and is_llm_configured()
    for index, (folder, outcome) in enumerate(folders, start=1):
        report(int(index / max(1, len(folders)) * 95), f"{folder.name} 처리 중")
        bid = BidNotice.objects.filter(source_ref=folder.name).first()
        if bid and mode == "skip":
            summary["skipped"] += 1
            continue
        if bid is None:
            bid = BidNotice.objects.create(
                title=folder.name, source_ref=folder.name, outcome=outcome
            )
            for path in sorted(p for p in folder.iterdir() if p.is_file() and not is_ignored(p)):
                if detect_format(path.name) is None:
                    continue
                with path.open("rb") as handle:
                    add_attachment(bid, file=handle, filename=path.name, sha256=file_sha256(path))
            summary["created"] += 1
        else:
            summary["updated"] += 1
        summary["bids"].append(bid.pk)
        if extract:
            try:
                extract_bid(bid)
                summary["extracted"] += 1
            except Exception as exc:  # keep loading the other bids
                summary["failed"].append({"folder": folder.name, "error": str(exc)[:300]})
    report(100, "완료")
    return summary
