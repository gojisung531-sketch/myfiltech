"""Draft endpoints (specs/10 초안 · PDF)."""

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bids.models import BidNotice
from apps.core.jobs import enqueue
from apps.core.permissions import IsBidManagerOrAdmin
from apps.core.serializers import JobSerializer
from apps.evaluation.models import RequirementEvaluation

from . import pdf, xlsx
from .models import DraftDocument, DraftType
from .serializers import DraftMetaSerializer, DraftSaveSerializer, DraftSerializer
from .service import DraftContentError, build_content, save_draft


class _DraftBase(APIView):
    permission_classes = [IsBidManagerOrAdmin]

    def bid(self, bid_pk) -> BidNotice:
        return get_object_or_404(BidNotice, pk=bid_pk)

    def doc_type(self, value: str) -> str:
        if value not in DraftType.values:
            raise NotFound("알 수 없는 초안 유형입니다.")
        return value

    def draft(self, bid, doc_type, version=None) -> DraftDocument:
        qs = DraftDocument.objects.filter(bid=bid, doc_type=doc_type).select_related("updated_by")
        draft = qs.filter(version=version).first() if version else qs.order_by("-version").first()
        if draft is None:
            raise NotFound("초안이 아직 생성되지 않았습니다.")
        return draft

    def version_param(self, request):
        value = request.query_params.get("version")
        if value in (None, ""):
            return None
        if not str(value).isdigit():
            raise ValidationError({"version": ["버전은 숫자여야 합니다."]})
        return int(value)


class DraftListView(_DraftBase):
    """GET /bids/{id}/drafts — latest version meta per type."""

    def get(self, request, bid_pk):
        bid = self.bid(bid_pk)
        result = []
        for doc_type in DraftType.values:
            latest = DraftDocument.latest(bid, doc_type)
            result.append(
                {
                    "doc_type": doc_type,
                    "doc_type_label": DraftType(doc_type).label,
                    "latest": DraftMetaSerializer(latest).data if latest else None,
                    "version_count": DraftDocument.objects.filter(
                        bid=bid, doc_type=doc_type
                    ).count(),
                }
            )
        return Response(result)


class DraftGenerateView(_DraftBase):
    """POST /bids/{id}/drafts/{type}/generate {new_version} → {job_id}"""

    def post(self, request, bid_pk, doc_type):
        bid = self.bid(bid_pk)
        doc_type = self.doc_type(doc_type)
        job = enqueue(
            "GENERATE_DRAFT",
            target=bid,
            payload={"doc_type": doc_type, "new_version": request.data.get("new_version") is True},
            user=request.user,
        )
        return Response(
            {"job_id": job.pk, "job": JobSerializer(job).data}, status=status.HTTP_202_ACCEPTED
        )


class DraftDetailView(_DraftBase):
    """GET /bids/{id}/drafts/{type}[?version=] · PUT (same version overwrite)."""

    def get(self, request, bid_pk, doc_type):
        draft = self.draft(self.bid(bid_pk), self.doc_type(doc_type), self.version_param(request))
        return Response(DraftSerializer(draft).data)

    def put(self, request, bid_pk, doc_type):
        serializer = DraftSaveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        draft = self.draft(self.bid(bid_pk), self.doc_type(doc_type), data.get("version"))
        try:
            save_draft(
                draft,
                content=data.get("content"),
                status=data.get("status"),
                title=data.get("title"),
                user=request.user,
            )
        except DraftContentError as exc:
            raise ValidationError({"content": [str(exc)]}) from exc
        return Response(DraftSerializer(draft).data)


class DraftVersionsView(_DraftBase):
    def get(self, request, bid_pk, doc_type):
        drafts = DraftDocument.objects.filter(
            bid=self.bid(bid_pk), doc_type=self.doc_type(doc_type)
        ).select_related("updated_by")
        return Response(DraftMetaSerializer(drafts.order_by("-version"), many=True).data)


def _pdf_response(content: bytes, name: str) -> HttpResponse:
    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = pdf.content_disposition(name)
    return response


class DraftPdfView(_DraftBase):
    """GET /bids/{id}/drafts/{type}/pdf[?version=]"""

    def get(self, request, bid_pk, doc_type):
        bid = self.bid(bid_pk)
        draft = self.draft(bid, self.doc_type(doc_type), self.version_param(request))
        html = pdf.draft_html(bid, draft.doc_type, draft.content, draft.version)
        return _pdf_response(pdf.render_pdf(html), pdf.filename(bid, draft.doc_type))


class DraftXlsxView(_DraftBase):
    """GET /bids/{id}/drafts/{type}/xlsx[?version=] — Compliance Matrix and checklist only."""

    def get(self, request, bid_pk, doc_type):
        bid = self.bid(bid_pk)
        doc_type = self.doc_type(doc_type)
        if doc_type not in xlsx.XLSX_TYPES:
            raise NotFound("XLSX는 Compliance Matrix와 입찰 체크리스트만 지원합니다.")
        draft = self.draft(bid, doc_type, self.version_param(request))
        response = HttpResponse(
            xlsx.render_xlsx(bid, doc_type, draft.content), content_type=xlsx.CONTENT_TYPE
        )
        response["Content-Disposition"] = pdf.content_disposition(
            pdf.filename(bid, doc_type, "xlsx")
        )
        return response


def evaluation_rows(bid) -> list[dict]:
    rows = []
    evaluations = RequirementEvaluation.objects.filter(requirement__bid=bid).select_related(
        "requirement__item"
    )
    for e in sorted(evaluations, key=lambda e: (e.requirement.order, e.requirement_id)):
        r = e.requirement
        rows.append(
            {
                "category": r.get_category_display(),
                "item": str(r.item) if r.item_id else "",
                "title": r.title,
                "requirement_text": r.requirement_text,
                "verdict": e.verdict,
                "verdict_label": e.get_verdict_display(),
                "risk_level": e.risk_level,
                "is_modified": e.is_modified,
                "rationale": e.rationale,
                "auto_answer": e.auto_answer,
                "action_items": e.action_items,
                "evidences": e.evidences,
            }
        )
    return rows


class BidReportPdfView(_DraftBase):
    """GET /bids/{id}/report.pdf — integrated report from the latest drafts (missing ones are
    built from rules on the fly, without saving or calling the LLM)."""

    def get(self, request, bid_pk):
        bid = self.bid(bid_pk)
        contents = {t: build_content(bid, t, request.user) for t in DraftType.values}
        html = pdf.report_html(bid, contents, evaluation_rows(bid))
        return _pdf_response(pdf.render_pdf(html), pdf.filename(bid, "REPORT"))
