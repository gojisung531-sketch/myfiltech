import hashlib

from django.db.models import Q
from django.http import FileResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.app_settings import get_setting
from apps.core.jobs import enqueue
from apps.core.permissions import IsAdminRole, ReadAnyWriteAdmin
from apps.core.serializers import JobSerializer

from .models import Document, DocumentMetadata, MetadataSchema
from .pipeline import STEPS
from .serializers import (
    DocumentMetadataSerializer,
    DocumentSerializer,
    DocumentUpdateSerializer,
    MetadataSchemaSerializer,
    TextDocumentSerializer,
)
from .validators import UploadRejected, validate_upload


def enqueue_extraction(document: Document, user, from_step: str = "parse", apply=None):
    return enqueue(
        "EXTRACT_DOCUMENT",
        target=document,
        payload={"from_step": from_step, "apply": apply},
        user=user,
    )


def _resolve_category(value, owner_type: str) -> MetadataSchema | None:
    if value in (None, ""):
        return None
    lookup = {"pk": int(value)} if str(value).isdigit() else {"code": value}
    schema = MetadataSchema.objects.filter(**lookup).first()
    if schema is None or schema.owner_type != owner_type:
        raise ValidationError({"category": ["분류를 찾을 수 없거나 문서 종류와 맞지 않습니다."]})
    return schema


def _sha256(uploaded) -> str:
    digest = hashlib.sha256()
    for chunk in uploaded.chunks():
        digest.update(chunk)
    uploaded.seek(0)
    return digest.hexdigest()


class DocumentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """/api/documents — read for all users, write for admins (specs/10)."""

    permission_classes = [ReadAnyWriteAdmin]
    serializer_class = DocumentSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        qs = Document.objects.select_related("category")
        params = self.request.query_params
        for field in ("owner_type", "status"):
            if params.get(field):
                qs = qs.filter(**{field: params[field]})
        if params.get("category"):
            qs = qs.filter(category__code=params["category"])
        if params.get("q"):
            q = params["q"]
            qs = qs.filter(Q(title__icontains=q) | Q(original_filename__icontains=q))
        return qs

    def retrieve(self, request, pk=None):
        data = DocumentSerializer(self.get_object()).data
        data["low_confidence_threshold"] = get_setting("extraction.low_confidence_threshold")
        return Response(data)

    def create(self, request):
        if request.content_type.startswith("multipart/"):
            return self._create_from_files(request)
        serializer = TextDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        category = data.get("category")
        if category is not None and category.owner_type != data["owner_type"]:
            raise ValidationError({"category": ["문서 종류와 맞지 않는 분류입니다."]})
        document = Document.objects.create(
            title=data["title"],
            source_text=data["source_text"],
            owner_type=data["owner_type"],
            file_format="TXT",
            category=category,
            category_source=Document.CategorySource.MANUAL if category else "AUTO",
            created_by=request.user,
        )
        job = enqueue_extraction(document, request.user)
        document.refresh_from_db()
        payload = {**DocumentSerializer(document).data, "job_id": job.pk, "duplicate_of": []}
        return Response({"documents": [payload], "skipped": []}, status=status.HTTP_201_CREATED)

    def _create_from_files(self, request):
        owner_type = request.data.get("owner_type")
        if owner_type not in ("COMPANY", "BID"):
            raise ValidationError({"owner_type": ["COMPANY 또는 BID 이어야 합니다."]})
        category = _resolve_category(request.data.get("category"), owner_type)
        files = request.FILES.getlist("files")
        if not files:
            raise ValidationError({"files": ["업로드할 파일을 선택하세요."]})

        created, skipped = [], []
        for uploaded in files:
            try:
                file_format = validate_upload(uploaded, owner_type)
            except UploadRejected as exc:
                skipped.append({"filename": uploaded.name, "reason": str(exc)})
                continue
            sha = _sha256(uploaded)
            duplicates = list(
                Document.objects.filter(sha256=sha, owner_type=owner_type).values_list(
                    "pk", flat=True
                )
            )
            document = Document(
                original_filename=uploaded.name,
                file_format=file_format,
                file_size=uploaded.size,
                sha256=sha,
                owner_type=owner_type,
                category=category,
                category_source=Document.CategorySource.MANUAL if category else "AUTO",
                created_by=request.user,
            )
            document.file.save(uploaded.name, uploaded, save=True)
            job = enqueue_extraction(document, request.user)
            document.refresh_from_db()
            created.append(
                {**DocumentSerializer(document).data, "job_id": job.pk, "duplicate_of": duplicates}
            )
        if not created:
            return Response(
                {"detail": "업로드된 파일이 없습니다.", "code": "invalid", "skipped": skipped},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"documents": created, "skipped": skipped}, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        document = self.get_object()
        serializer = DocumentUpdateSerializer(document, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        reextract = serializer.validated_data.pop("reextract", False)
        category_changed = (
            "category" in serializer.validated_data
            and serializer.validated_data["category"] != document.category
        )
        document = serializer.save()
        if category_changed:
            document.category_source = Document.CategorySource.MANUAL
            document.category_confidence = None
            document.save(update_fields=["category_source", "category_confidence"])
        job = enqueue_extraction(document, request.user, "extract") if reextract else None
        document.refresh_from_db()
        return Response({**DocumentSerializer(document).data, "job_id": job.pk if job else None})

    def perform_destroy(self, instance):
        if instance.file:
            instance.file.delete(save=False)
        instance.delete()

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        document = self.get_object()
        if not document.file:
            raise NotFound("원본 파일이 없는 문서입니다 (텍스트 입력).")
        return FileResponse(
            document.file.open("rb"), as_attachment=True, filename=document.original_filename
        )

    @action(detail=True, methods=["get"])
    def text(self, request, pk=None):
        document = self.get_object()
        text = document.extracted_text or ""
        return Response(
            {
                "pages": text.split("\f") if text else [],
                "page_count": document.page_count,
                "tables": document.extracted_tables,
            }
        )

    @action(detail=True, methods=["post"], permission_classes=[IsAdminRole])
    def reprocess(self, request, pk=None):
        document = self.get_object()
        from_step = request.data.get("from_step", "parse")
        if from_step not in STEPS:
            raise ValidationError({"from_step": [f"{', '.join(STEPS)} 중 하나여야 합니다."]})
        job = enqueue_extraction(document, request.user, from_step, request.data.get("apply"))
        return Response({"job_id": job.pk, "job": JobSerializer(job).data})

    @action(
        detail=True, methods=["get"], url_path="mapping-preview", permission_classes=[IsAdminRole]
    )
    def mapping_preview(self, request, pk=None):
        from apps.company.mapping import MappingError, preview

        try:
            changes = preview(self.get_object())
        except MappingError as exc:
            raise ValidationError({"detail": [str(exc)]}) from exc
        return Response({"changes": [c.as_dict() for c in changes]})

    @action(detail=True, methods=["post"], permission_classes=[IsAdminRole])
    def apply(self, request, pk=None):
        from apps.company.mapping import MappingError, apply

        document = self.get_object()
        if document.owner_type != "COMPANY":
            raise ValidationError({"detail": ["회사 자료 문서만 반영할 수 있습니다."]})
        try:
            changes = apply(document)
        except MappingError as exc:
            raise ValidationError({"detail": [str(exc)]}) from exc
        document.refresh_from_db()
        return Response(
            {
                "changes": [c.as_dict() for c in changes],
                "document": DocumentSerializer(document).data,
            }
        )


class DocumentMetadataViewSet(viewsets.ModelViewSet):
    """/api/documents/{document_pk}/metadata — admin edits lock the value (specs/04 §2.4)."""

    permission_classes = [ReadAnyWriteAdmin]
    serializer_class = DocumentMetadataSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete"]

    def get_document(self) -> Document:
        document = Document.objects.filter(pk=self.kwargs["document_pk"]).first()
        if document is None:
            raise NotFound("문서를 찾을 수 없습니다.")
        return document

    def get_queryset(self):
        return DocumentMetadata.objects.filter(document_id=self.kwargs["document_pk"])

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "document": self.get_document()}

    def perform_create(self, serializer):
        serializer.save(
            document=self.get_document(),
            source=DocumentMetadata.Source.MANUAL,
            is_locked=True,
            updated_by=self.request.user,
        )

    def perform_update(self, serializer):
        unlock = serializer.validated_data.get("is_locked") is False
        content_changed = any(k != "is_locked" for k in serializer.validated_data)
        extra = {"updated_by": self.request.user}
        if content_changed:
            extra.update(source=DocumentMetadata.Source.MANUAL, confidence=None)
        if not unlock:
            extra["is_locked"] = True
        serializer.save(**extra)


class MetadataSchemaViewSet(viewsets.ModelViewSet):
    permission_classes = [ReadAnyWriteAdmin]
    serializer_class = MetadataSchemaSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        qs = MetadataSchema.objects.all()
        owner_type = self.request.query_params.get("owner_type")
        return qs.filter(owner_type=owner_type) if owner_type else qs

    def perform_destroy(self, instance):
        if instance.documents.exists():
            raise ValidationError(
                {
                    "detail": [
                        "이 분류를 사용하는 문서가 있습니다. 비활성화하거나 문서 분류를 먼저 바꾸세요."
                    ]
                }
            )
        instance.delete()

    @action(detail=True, methods=["post"])
    def reextract(self, request, pk=None):
        schema = self.get_object()
        jobs = [
            enqueue_extraction(document, request.user, "extract").pk
            for document in schema.documents.all()
        ]
        return Response({"job_ids": jobs, "count": len(jobs)})


class LoadInitialDataView(APIView):
    """POST /api/admin/load-initial-data {mode} → job"""

    permission_classes = [IsAdminRole]

    def post(self, request):
        mode = request.data.get("mode", "skip")
        if mode not in ("skip", "update"):
            raise ValidationError({"mode": ["skip 또는 update"]})
        job = enqueue("LOAD_INITIAL_DATA", payload={"mode": mode}, user=request.user)
        return Response({"job_id": job.pk, "job": JobSerializer(job).data}, status=202)
