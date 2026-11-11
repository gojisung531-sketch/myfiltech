"""Input provenance and read-only freshness, with fail-closed execution boundaries."""

import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.utils import timezone

from .models import AnalysisRun

SCHEMA = "b6c.inputs.v1"
LABELS = {
    "company": "회사 정보",
    "company_sources": "회사 원본 연결",
    "products": "제품 자료",
    "test_reports": "성적서",
    "certificates": "인증 자료",
    "deliveries": "납품 실적",
    "delivery_products": "실적 제품 연결",
    "documents": "관련 원본/추출 텍스트",
    "metadata": "원본 메타데이터",
    "source_files": "원본 파일 바이트/가용성",
    "schemas": "관련 메타데이터 정의",
    "bid": "공고 정보",
    "requirements": "요구조건",
    "items": "품목 및 사용자 제품 선택",
    "candidates": "제품 후보",
    "settings": "분석 정책/설정",
    "llm_settings": "모델/생성 설정",
    "prompts": "활성 프롬프트",
    "engine": "규칙/생성 코드",
    "reference": "기준일/모드",
    "evaluations": "초안 입력 판정",
}
ENGINE_FILES = [
    "apps/core/freshness.py",
    "apps/core/defaults.py",
    "apps/core/evaluation_policy.py",
    "apps/core/units.py",
    "apps/evaluation/context.py",
    "apps/evaluation/rules.py",
    "apps/evaluation/grades.py",
    "apps/evaluation/evidence.py",
    "apps/evaluation/formal_sources.py",
    "apps/evaluation/assessment.py",
    "apps/evaluation/models.py",
    "apps/evaluation/service.py",
    "apps/drafts/generators.py",
    "apps/drafts/service.py",
    "apps/llm/services.py",
]


def canonical(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, ensure_ascii=False))


def digest(value):
    return hashlib.sha256(
        json.dumps(
            canonical(value), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def _rows(queryset, exclude=()):
    fields = [f.attname for f in queryset.model._meta.concrete_fields if f.name not in exclude]
    return list(queryset.order_by("pk").values(*fields))


def _models():
    from apps.bids.models import BidAttachment, BidItem, BidNotice, BidProductMatch, BidRequirement
    from apps.company.models import Certificate, Company, DeliveryRecord, Product, TestReport
    from apps.documents.models import Document, DocumentMetadata, MetadataSchema
    from apps.drafts.models import DraftDocument
    from apps.evaluation.models import EvaluationHistory, RequirementEvaluation
    from apps.llm.models import LLMModelOption, LLMSettings, PromptTemplate

    from .models import AppSetting

    return [
        Company,
        Company.source_documents.through,
        Product,
        TestReport,
        Certificate,
        DeliveryRecord,
        DeliveryRecord.products.through,
        Document,
        DocumentMetadata,
        MetadataSchema,
        BidNotice,
        BidAttachment,
        BidItem,
        BidProductMatch,
        BidRequirement,
        RequirementEvaluation,
        EvaluationHistory,
        DraftDocument,
        AppSetting,
        LLMSettings,
        LLMModelOption,
        PromptTemplate,
    ]


def _lock_inputs():
    # Short transaction boundary only. Also blocks phantoms (new/deleted rows) during
    # the final comparison+save. Never hold these locks during a provider request.
    if connection.vendor == "postgresql":
        names = sorted(connection.ops.quote_name(model._meta.db_table) for model in _models())
        with connection.cursor() as cursor:
            cursor.execute("LOCK TABLE " + ", ".join(names) + " IN SHARE ROW EXCLUSIVE MODE")


def capture_inputs(bid_id, kind):
    """A consistent DB read; raw files are fingerprinted, never reparsed/copied here."""
    outer = connection.in_atomic_block
    with transaction.atomic():
        if connection.vendor == "postgresql" and not outer:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        return _capture(bid_id, kind)


def _capture(bid_id, kind):
    from apps.bids.models import BidAttachment, BidItem, BidNotice, BidProductMatch, BidRequirement
    from apps.company.models import Certificate, Company, DeliveryRecord, Product, TestReport
    from apps.documents.models import Document, DocumentMetadata, MetadataSchema
    from apps.evaluation.context import reference_date
    from apps.evaluation.models import RequirementEvaluation
    from apps.llm.models import LLMModelOption, LLMSettings, PromptTemplate

    from .app_settings import get_setting
    from .defaults import APP_SETTING_DEFAULTS
    from .models import AppSetting

    bid = BidNotice.objects.get(pk=bid_id)
    products, reports = Product.objects.all(), TestReport.objects.all()
    certs, deliveries = Certificate.objects.all(), DeliveryRecord.objects.all()
    document_ids = set(
        Company.source_documents.through.objects.values_list("document_id", flat=True)
    )
    document_ids.update(
        BidAttachment.objects.filter(bid_id=bid_id).values_list("document_id", flat=True)
    )
    for query in [products, reports, certs, deliveries]:
        document_ids.update(
            query.exclude(source_document=None).values_list("source_document_id", flat=True)
        )
    documents = list(Document.objects.filter(pk__in=document_ids).order_by("pk"))
    file_hashes = []
    for doc in documents:
        item = {
            "id": doc.pk,
            "recorded_sha256": doc.sha256,
            "actual_sha256": None,
            "state": "NO_FILE",
        }
        if doc.file:
            try:
                with doc.file.open("rb") as stream:
                    item.update(
                        actual_sha256=hashlib.file_digest(stream, "sha256").hexdigest(),
                        state="AVAILABLE",
                    )
            except OSError:
                item["state"] = "UNAVAILABLE"
        file_hashes.append(item)
    ref, simulation = reference_date(bid)
    keys = [
        k
        for k in APP_SETTING_DEFAULTS
        if k.startswith(("evaluation.", "matching.", "report.", "company.", "llm.max_input_chars"))
    ]
    stored = dict(AppSetting.objects.filter(key__in=keys).values_list("key", "value"))
    model_ids = LLMSettings.objects.exclude(active_model=None).values_list(
        "active_model_id", flat=True
    )
    values = {
        "company": _rows(Company.objects.all()),
        "company_sources": _rows(Company.source_documents.through.objects.all()),
        "products": _rows(products),
        "test_reports": _rows(reports),
        "certificates": _rows(certs),
        "deliveries": _rows(deliveries),
        "delivery_products": _rows(DeliveryRecord.products.through.objects.all()),
        "documents": _rows(Document.objects.filter(pk__in=document_ids)),
        "metadata": _rows(DocumentMetadata.objects.filter(document_id__in=document_ids)),
        "schemas": _rows(
            MetadataSchema.objects.filter(
                pk__in=[d.category_id for d in documents if d.category_id]
            )
        ),
        "source_files": file_hashes,
        "bid": _rows(
            BidNotice.objects.filter(pk=bid_id),
            exclude=(
                "created_at",
                "updated_at",
                "processing_status",
                "processing_error",
                "extra",
                "fit_score",
                "fit_reason",
                "review_status",
                "reviewed_at",
                "reviewed_by",
                "outcome",
            ),
        ),
        "requirements": _rows(BidRequirement.objects.filter(bid_id=bid_id)),
        "items": _rows(BidItem.objects.filter(bid_id=bid_id)),
        "candidates": _rows(BidProductMatch.objects.filter(bid_id=bid_id)),
        "settings": {key: stored.get(key, APP_SETTING_DEFAULTS[key].value) for key in sorted(keys)},
        # Provider key tables, credentials, tokens and connection URLs are never read.
        "llm_settings": {
            "settings": _rows(LLMSettings.objects.all(), exclude=("created_at", "updated_at")),
            "models": _rows(
                LLMModelOption.objects.filter(pk__in=model_ids),
                exclude=("created_at", "updated_at"),
            ),
        },
        "prompts": _rows(
            PromptTemplate.objects.filter(is_active=True).filter(
                key__regex=r"^(evaluation\.|draft\.)"
            ),
            exclude=("created_at", "updated_at", "updated_by"),
        ),
        "engine": {
            name: hashlib.sha256((Path(settings.BACKEND_DIR) / name).read_bytes()).hexdigest()
            for name in ENGINE_FILES
        },
        "reference": {
            "date": str(ref),
            "is_simulation": simulation,
            "mode": get_setting("evaluation.reference_date_mode"),
        },
    }
    if kind == "DRAFT":
        values["evaluations"] = _rows(
            RequirementEvaluation.objects.filter(requirement__bid_id=bid_id)
        )
        values["draft_bid_state"] = {
            "fit_score": bid.fit_score,
            "fit_reason": bid.fit_reason,
            "extra": bid.extra,
        }
    return canonical({"schema": SCHEMA, "kind": kind, "components": values})


def _guard(bid_id, kind):
    from apps.drafts.models import DraftDocument
    from apps.evaluation.models import RequirementEvaluation

    query = (
        DraftDocument.objects.filter(bid_id=bid_id)
        if kind == "DRAFT"
        else RequirementEvaluation.objects.filter(requirement__bid_id=bid_id)
    )
    return digest(_rows(query))


class InputsChanged(ValueError):
    pass


def begin_run(bid_id, kind, options=None):
    with transaction.atomic():
        _lock_inputs()
        from apps.company.models import Company

        Company.load()  # explicit execution's existing singleton initialization, never on GET
        inputs = capture_inputs(bid_id, kind)
        return AnalysisRun.objects.create(
            bid_id=bid_id,
            kind=kind,
            inputs=inputs,
            input_hash=digest(inputs),
            guard_hash=_guard(bid_id, kind),
            options=canonical(options or {}),
            started_at=timezone.now(),
        )


def fail_run(run, code):
    run.state, run.failure_code = "FAILED", code
    run.completed_at = timezone.now()
    run.save(update_fields=["state", "failure_code", "completed_at"])


@contextmanager
def finish_run(run):
    """All results commit together, or none do; preserve concurrent manual edits."""
    with transaction.atomic():
        _lock_inputs()
        current = capture_inputs(run.bid_id, run.kind)
        if digest(current) != run.input_hash or _guard(run.bid_id, run.kind) != run.guard_hash:
            raise InputsChanged("INPUTS_OR_MANUAL_RESULTS_CHANGED_DURING_EXECUTION")
        yield
        if digest(capture_inputs(run.bid_id, run.kind)) != run.input_hash:
            raise InputsChanged("INPUTS_CHANGED_DURING_RESULT_COMMIT")
        run.state, run.completed_at = "COMPLETED", timezone.now()
        run.save(update_fields=["state", "completed_at", "outputs"])


def output_snapshot(obj):
    from apps.drafts.models import DraftDocument

    if isinstance(obj, DraftDocument):
        fields = (
            "doc_type",
            "title",
            "content",
            "version",
            "generated_by",
            "is_modified",
            "used_llm",
        )
    else:
        fields = (*obj.SNAPSHOT_FIELDS, "rule_trace", "ai_verdict", "ai_answer", "is_modified")
    return canonical({field: getattr(obj, field) for field in fields if field != "analysis_run_id"})


def _changes(before, after):
    reasons = []
    for key in sorted(set(before) | set(after)):
        if digest(before.get(key)) == digest(after.get(key)):
            continue
        reason = {"code": key.upper() + "_CHANGED", "component": key, "label": LABELS.get(key, key)}
        a, b = before.get(key), after.get(key)
        if (
            isinstance(a, list)
            and isinstance(b, list)
            and all(isinstance(r, dict) and "id" in r for r in a + b)
        ):
            a, b = {r["id"]: r for r in a}, {r["id"]: r for r in b}
            reason.update(
                added_ids=sorted(set(b) - set(a)),
                deleted_ids=sorted(set(a) - set(b)),
                modified_ids=sorted(k for k in set(a) & set(b) if digest(a[k]) != digest(b[k])),
            )
        reasons.append(reason)
    return reasons


class FreshnessReader:
    """No get_or_create, save, jobs or paid work in this read path."""

    def __init__(self):
        self.current = {}
        self.states = {}
        self.evaluation_summaries = {}

    def inputs(self, bid_id, kind):
        key = bid_id, kind
        if key not in self.current:
            self.current[key] = capture_inputs(bid_id, kind)
        return self.current[key]

    def result(self, obj, kind=None):
        from apps.drafts.models import DraftDocument

        kind = kind or ("DRAFT" if isinstance(obj, DraftDocument) else "EVALUATION")
        bid_id = obj.bid_id if kind == "DRAFT" else obj.requirement.bid_id
        result = {
            "status": "UNKNOWN",
            "status_label": "확인 불가",
            "analysis_at": None,
            "result_saved_at": str(obj.created_at),
            "last_edited_at": str(obj.updated_at),
            "analysis_run_id": obj.analysis_run_id,
            "input_hash": None,
            "current_input_hash": None,
            "reasons": [],
            "manual_modified": obj.is_modified,
            "requires_review": True,
            "automatic_refresh": False,
        }
        if not obj.analysis_run_id:
            result["reasons"] = [
                {"code": "LEGACY_INPUTS_UNKNOWN", "label": "보존된 전체 실행 입력 없음"}
            ]
            return result
        run = obj.analysis_run
        result.update(
            analysis_at=str(run.started_at),
            analysis_completed_at=str(run.completed_at) if run.completed_at else None,
            input_hash=run.input_hash,
        )
        if (
            run.state != "COMPLETED"
            or run.inputs.get("schema") != SCHEMA
            or digest(run.inputs) != run.input_hash
            or run.kind != kind
            or run.bid_id != bid_id
        ):
            result["reasons"] = [
                {"code": "INPUT_PROVENANCE_UNVERIFIABLE", "label": "실행 입력/완료 상태 확인 불가"}
            ]
            return result
        expected = run.outputs.get(str(obj.pk))
        if expected is None:
            result["reasons"] = [
                {"code": "RUN_OUTPUT_NOT_RECORDED", "label": "실행에 연결된 결과 스냅샷 없음"}
            ]
            return result
        if not obj.is_modified and expected != output_snapshot(obj):
            result["reasons"] = [
                {"code": "UNTRACKED_RESULT_EDIT", "label": "수동 수정 표시 없이 결과가 변경됨"}
            ]
            return result
        if any(row["state"] == "UNAVAILABLE" for row in run.inputs["components"]["source_files"]):
            result["reasons"] = [
                {
                    "code": "INPUT_FILE_UNAVAILABLE_AT_EXECUTION",
                    "label": "실행 당시 원본 파일 식별정보 불완전",
                }
            ]
            return result
        key = run.pk
        if key not in self.states:
            current = self.inputs(bid_id, kind)
            self.states[key] = (
                digest(current),
                _changes(run.inputs["components"], current["components"]),
            )
        current_hash, reasons = self.states[key]
        reasons = list(reasons)
        result["current_input_hash"] = current_hash
        if kind == "DRAFT":
            upstream = self.evaluations(bid_id)
            result["upstream_evaluations"] = upstream
            if upstream["status"] == "UNKNOWN" and not reasons:
                result["reasons"] = [
                    {
                        "code": "UPSTREAM_INPUTS_UNKNOWN",
                        "label": "초안에 사용한 판정 입력 확인 불가",
                    }
                ]
                return result
            if upstream["status"] == "STALE":
                reasons.append(
                    {"code": "UPSTREAM_EVALUATIONS_STALE", "label": "입력 판정 갱신 필요"}
                )
        result["status"] = "STALE" if reasons else "CURRENT"
        result["status_label"] = "갱신 필요" if reasons else "현재 입력과 일치"
        result["generated_result_unchanged"] = (
            expected == output_snapshot(obj) if expected else None
        )
        result["reasons"] = reasons
        result["requires_review"] = bool(
            reasons or obj.is_modified or not result["generated_result_unchanged"]
        )
        return result

    def evaluations(self, bid_id):
        from apps.bids.models import BidRequirement
        from apps.evaluation.models import RequirementEvaluation

        if bid_id not in self.evaluation_summaries:
            rows = list(
                RequirementEvaluation.objects.filter(requirement__bid_id=bid_id).select_related(
                    "analysis_run", "requirement"
                )
            )
            states = [self.result(row, "EVALUATION") for row in rows]
            statuses = [s["status"] for s in states]
            missing = BidRequirement.objects.filter(bid_id=bid_id).count() - len(rows)
            status = (
                "STALE"
                if "STALE" in statuses
                else "UNKNOWN"
                if not states or "UNKNOWN" in statuses or missing
                else "CURRENT"
            )
            self.evaluation_summaries[bid_id] = {
                "status": status,
                "missing_evaluations": missing,
                "counts": {key: statuses.count(key) for key in ["CURRENT", "STALE", "UNKNOWN"]},
                "results": [
                    {"requirement_id": row.requirement_id, "evaluation_id": row.pk, **state}
                    for row, state in zip(rows, states, strict=True)
                ],
                "automatic_refresh": False,
            }
        return self.evaluation_summaries[bid_id]

    def summary(self, bid_id):
        from apps.drafts.models import DraftDocument

        return {
            "evaluations": self.evaluations(bid_id),
            "drafts": [
                {
                    "id": draft.pk,
                    "doc_type": draft.doc_type,
                    "version": draft.version,
                    "freshness": self.result(draft),
                }
                for draft in DraftDocument.objects.filter(bid_id=bid_id).select_related(
                    "analysis_run"
                )
            ],
            "observed_current_input_hash": digest(self.inputs(bid_id, "EVALUATION")),
            "observed_at": timezone.now().isoformat(),
            "automatic_refresh": False,
        }


def reader_for(context):
    if "freshness_reader" not in context:
        context["freshness_reader"] = FreshnessReader()
    return context["freshness_reader"]
