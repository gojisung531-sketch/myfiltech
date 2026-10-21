from rest_framework import serializers

from .evidence import evidence_document_map
from .models import EvaluationHistory, RequirementEvaluation, RiskLevel, Verdict


class EvidenceSerializer(serializers.Serializer):
    type = serializers.CharField(max_length=30)
    id = serializers.IntegerField(required=False, default=0)
    label = serializers.CharField(max_length=500)
    page = serializers.IntegerField(required=False, default=0, allow_null=True)
    quote = serializers.CharField(required=False, allow_blank=True, default="")


class EvaluationSerializer(serializers.ModelSerializer):
    verdict_label = serializers.CharField(source="get_verdict_display", read_only=True)
    risk_level_label = serializers.CharField(source="get_risk_level_display", read_only=True)
    decided_by_label = serializers.CharField(source="get_decided_by_display", read_only=True)
    ai_verdict_label = serializers.CharField(source="get_ai_verdict_display", read_only=True)
    modified_by_name = serializers.SerializerMethodField()
    verdict = serializers.ChoiceField(choices=Verdict.choices)
    risk_level = serializers.ChoiceField(choices=RiskLevel.choices)
    action_items = serializers.ListField(
        child=serializers.CharField(allow_blank=True), required=False
    )
    evidences = EvidenceSerializer(many=True, required=False)

    class Meta:
        model = RequirementEvaluation
        fields = [
            "id",
            "requirement",
            "verdict",
            "verdict_label",
            "risk_level",
            "risk_level_label",
            "company_value",
            "auto_answer",
            "rationale",
            "action_items",
            "clarification_question",
            "evidences",
            "decided_by",
            "decided_by_label",
            "rule_trace",
            "ai_verdict",
            "ai_verdict_label",
            "ai_answer",
            "is_modified",
            "modified_by_name",
            "modified_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "requirement",
            "decided_by",
            "rule_trace",
            "ai_verdict",
            "ai_answer",
            "is_modified",
            "modified_at",
            "updated_at",
        ]

    def get_modified_by_name(self, obj) -> str | None:
        user = obj.modified_by
        return (user.display_name or user.username) if user else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        doc_map = self.context.get("doc_map")
        if doc_map is None:
            doc_map = evidence_document_map([instance.evidences])
        for evidence in data.get("evidences") or []:
            evidence["document_id"] = doc_map.get((evidence.get("type"), evidence.get("id")))
        return data


class HistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = EvaluationHistory
        fields = ["id", "snapshot", "changed_by_name", "changed_at"]

    def get_changed_by_name(self, obj) -> str | None:
        user = obj.changed_by
        return (user.display_name or user.username) if user else None
