from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.permissions import IsBidManagerOrAdmin

from .models import RequirementEvaluation
from .serializers import EvaluationSerializer, HistorySerializer
from .service import revert_evaluation, update_evaluation


class EvaluationViewSet(mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """PATCH /evaluations/{id}, POST …/revert, GET …/history (specs/10 판정)."""

    permission_classes = [IsBidManagerOrAdmin]
    serializer_class = EvaluationSerializer
    queryset = RequirementEvaluation.objects.select_related("requirement__bid", "modified_by")
    http_method_names = ["get", "post", "patch"]

    def partial_update(self, request, *args, **kwargs):
        evaluation = self.get_object()
        serializer = self.get_serializer(evaluation, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        evaluation = update_evaluation(evaluation, serializer.validated_data, request.user)
        return Response(self.get_serializer(evaluation).data)

    @action(detail=True, methods=["post"])
    def revert(self, request, pk=None):
        try:
            evaluation = revert_evaluation(self.get_object(), request.user)
        except ValueError as exc:
            raise ValidationError({"detail": [str(exc)]}) from exc
        return Response(self.get_serializer(evaluation).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        evaluation = self.get_object()
        rows = evaluation.history.select_related("changed_by")
        return Response(HistorySerializer(rows, many=True).data)
