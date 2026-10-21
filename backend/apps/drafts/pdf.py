"""HTML → PDF with WeasyPrint (specs/09 §5)."""

from urllib.parse import quote

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from apps.company.models import Company
from apps.core.app_settings import get_setting

from .models import DraftType

FILE_LABELS = {
    DraftType.COMPLIANCE_MATRIX: "ComplianceMatrix",
    DraftType.BID_CHECKLIST: "입찰체크리스트",
    DraftType.TECHNICAL_QUERY: "기술질의서",
    DraftType.REVIEW_REPORT: "검토보고서",
    "REPORT": "통합보고서",
}
RECOMMENDATION_LABELS = {
    "BID": "입찰 권고",
    "CONDITIONAL": "조건부 입찰",
    "NO_BID": "입찰 불참 권고",
}


def css_string(value) -> str:
    """Quote a value for a CSS `content:` string."""
    text = " ".join(str(value or "").split())
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def filename(bid, kind: str, ext: str = "pdf") -> str:
    stamp = timezone.localdate().strftime("%Y%m%d")
    return f"{bid.notice_no or bid.pk}_{FILE_LABELS[kind]}_{stamp}.{ext}"


def content_disposition(name: str) -> str:
    """RFC 5987: ASCII fallback + UTF-8 filename* (specs/09 §5)."""
    fallback = name.encode("ascii", "ignore").decode() or "document"
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(name)}"


def base_context(bid, title: str) -> dict:
    company = Company.load()
    logo = get_setting("report.company_logo")
    return {
        "bid": bid,
        "company": company,
        "title": title,
        "font_dir": settings.FONTS_DIR.as_uri(),
        "logo": logo if isinstance(logo, str) and logo.startswith(("data:", "http")) else "",
        "header_left": css_string(company.name),
        "header_right": css_string(
            f"공고번호 {bid.notice_no}" if bid.notice_no else bid.title[:40]
        ),
        "footer_left": css_string(
            f"생성 {timezone.localtime():%Y-%m-%d %H:%M} · {get_setting('report.disclaimer') or ''}"
        ),
        "recommendation_labels": RECOMMENDATION_LABELS,
        "disclaimer": get_setting("report.disclaimer") or "",
    }


def render_pdf(html: str) -> bytes:
    from weasyprint import HTML

    return HTML(string=html, base_url=str(settings.BACKEND_DIR)).write_pdf()


def draft_html(bid, doc_type: str, content: dict, version: int | None = None) -> str:
    context = base_context(bid, DraftType(doc_type).label)
    context.update(
        {
            "sections": [
                {"type": doc_type, "label": DraftType(doc_type).label, "content": content}
            ],
            "version": version,
        }
    )
    return render_to_string("pdf/document.html", context)


def report_html(bid, contents: dict, evaluations: list) -> str:
    """통합 보고서: 표지 → 검토 보고서 → 요구사항·판정 → CM → 체크리스트 → 기술질의서."""
    context = base_context(bid, "입찰 검토 통합 보고서")
    order = [
        DraftType.REVIEW_REPORT,
        "EVALUATIONS",
        DraftType.COMPLIANCE_MATRIX,
        DraftType.BID_CHECKLIST,
        DraftType.TECHNICAL_QUERY,
    ]
    sections = []
    for kind in order:
        if kind == "EVALUATIONS":
            sections.append({"type": kind, "label": "요구사항 · 판정", "content": evaluations})
        else:
            sections.append(
                {"type": kind, "label": DraftType(kind).label, "content": contents[kind]}
            )
    context.update({"sections": sections, "cover": True})
    return render_to_string("pdf/document.html", context)
