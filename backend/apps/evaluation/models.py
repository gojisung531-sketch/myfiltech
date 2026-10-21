"""Requirement evaluations (specs/02 §6)."""

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Verdict(models.TextChoices):
    MET = "MET", "충족"
    NEEDS_SUPPLEMENT = "NEEDS_SUPPLEMENT", "보완 필요"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION", "확인 필요"


class RiskLevel(models.TextChoices):
    LOW = "LOW", "낮음"
    MEDIUM = "MEDIUM", "보통"
    HIGH = "HIGH", "높음"


RISK_ORDER = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}


class RequirementEvaluation(TimeStampedModel):
    class DecidedBy(models.TextChoices):
        RULE = "RULE", "규칙"
        LLM = "LLM", "LLM"
        RULE_LLM = "RULE+LLM", "규칙+LLM"
        MANUAL = "MANUAL", "수동"

    requirement = models.OneToOneField(
        "bids.BidRequirement", on_delete=models.CASCADE, related_name="evaluation"
    )
    verdict = models.CharField(max_length=20, choices=Verdict.choices)
    risk_level = models.CharField(max_length=10, choices=RiskLevel.choices, default=RiskLevel.LOW)
    company_value = models.TextField(blank=True)
    auto_answer = models.TextField(blank=True)
    rationale = models.TextField(blank=True)
    action_items = models.JSONField(default=list, blank=True)
    clarification_question = models.TextField(blank=True)
    evidences = models.JSONField(default=list, blank=True)
    decided_by = models.CharField(max_length=10, choices=DecidedBy.choices)
    rule_trace = models.JSONField(default=dict, blank=True)
    ai_verdict = models.CharField(max_length=20, choices=Verdict.choices, blank=True)
    ai_answer = models.TextField(blank=True)
    is_modified = models.BooleanField(default=False)
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    modified_at = models.DateTimeField(null=True, blank=True)
    llm_call = models.ForeignKey(
        "llm.LLMCallLog", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["requirement__order", "requirement_id"]

    def __str__(self):
        return f"{self.requirement_id}: {self.verdict}"

    SNAPSHOT_FIELDS = [
        "verdict",
        "risk_level",
        "company_value",
        "auto_answer",
        "rationale",
        "action_items",
        "clarification_question",
        "evidences",
        "decided_by",
    ]

    def snapshot(self) -> dict:
        return {name: getattr(self, name) for name in self.SNAPSHOT_FIELDS}


class EvaluationHistory(models.Model):
    """One row per save: automatic (changed_by=None) or manual (specs/08 §8)."""

    evaluation = models.ForeignKey(
        RequirementEvaluation, on_delete=models.CASCADE, related_name="history"
    )
    snapshot = models.JSONField()
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at", "-id"]

    def __str__(self):
        return f"{self.evaluation_id} @ {self.changed_at:%Y-%m-%d %H:%M}"
