"""Explicit B5A stored-policy upgrade. No seeds, provider changes or LLM execution."""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction

from apps.core.app_settings import set_setting
from apps.core.evaluation_policy import VERDICT_DEFINITIONS
from apps.core.logging import mask_secrets
from apps.core.models import AppSetting
from apps.llm.models import PromptTemplate
from apps.llm.prompt_defaults import COMMON_SYSTEM, COMMON_SYSTEM_BASE, PROMPTS

SETTING_KEY = "evaluation.verdict_definitions"
# Only this known pre-B4B seed is eligible for automatic replacement.
LEGACY_DEFINITIONS = """MET(충족): 회사 자료(사양서/성적서/인증서/실적)에 요구사항을 만족함을 직접 입증하는 근거가 있고 유효함.
NEEDS_SUPPLEMENT(보완 필요): 회사가 대응 가능성은 있으나 증빙·사양·유효기간·시험규격이 부족하거나 다름
  (예: 인증 만료, 다른 규격 성적서만 보유, 주문제작 옵션, 시험 추가 필요, 요구 미달로 사양 변경 필요).
NEEDS_CONFIRMATION(확인 필요): 공고 요구가 모호하거나 회사 자료가 없어 판단 불가 → 발주처 질의 또는 내부 확인 필요.
규칙 엔진 결과(rule_result.verdict)가 있으면 그 판정을 바꾸지 말고 근거 서술과 답변만 작성합니다."""


class Command(BaseCommand):
    help = (
        "판정 정책 변경 계획을 확인합니다. --apply는 로컬 백업 후 새 프롬프트 버전을 활성화합니다."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--backup", help="새 백업 JSON 경로 (backend/.venv 내부)")

    @transaction.atomic
    def handle(self, *args, **options):
        setting = AppSetting.objects.select_for_update().filter(key=SETTING_KEY).first()
        if setting is None or setting.value not in (LEGACY_DEFINITIONS, VERDICT_DEFINITIONS):
            raise CommandError(
                "저장 판정 정의가 알려진 기본값과 다릅니다. 수동 정책 검토가 필요합니다."
            )

        keys = [p["key"] for p in PROMPTS]
        versions = list(PromptTemplate.objects.select_for_update().filter(key__in=keys))
        active = {p.key: p for p in versions if p.is_active}
        if set(active) != set(keys):
            raise CommandError("활성 프롬프트가 누락되었습니다. 초기화하지 않고 중단합니다.")
        targets = []
        for key, prompt in sorted(active.items()):
            if prompt.system_prompt == COMMON_SYSTEM:
                continue
            if prompt.system_prompt != COMMON_SYSTEM_BASE:
                raise CommandError(f"{key}: 수동 시스템 프롬프트를 먼저 검토해야 합니다.")
            default = next(p for p in PROMPTS if p["key"] == key)
            if prompt.user_prompt_template != default["user_prompt_template"]:
                raise CommandError(f"{key}: 수동 작업 프롬프트의 정책 충돌을 먼저 검토해야 합니다.")
            targets.append(prompt)

        change_setting = setting.value != VERDICT_DEFINITIONS
        plan = {
            "setting_changed": change_setting,
            "prompts": [
                {
                    "key": p.key,
                    "from": p.version,
                    "to": max(v.version for v in versions if v.key == p.key) + 1,
                }
                for p in targets
            ],
        }
        if not options["apply"] or not (change_setting or targets):
            self.stdout.write(json.dumps({"applied": False, **plan}, ensure_ascii=False))
            return
        if not options["backup"]:
            raise CommandError("--apply에는 --backup이 필요합니다.")
        backup = Path(options["backup"]).resolve()
        if not backup.is_relative_to((settings.BACKEND_DIR / ".venv").resolve()):
            raise CommandError("백업은 Git 제외 경로 backend/.venv 내부에만 저장합니다.")
        payload = {
            "scope": "B5A evaluation policy only",
            "setting": AppSetting.objects.filter(pk=setting.pk).values().get(),
            "prompts": list(PromptTemplate.objects.filter(pk__in=[p.pk for p in targets]).values()),
            "plan": plan,
        }
        encoded = json.dumps(payload, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2)
        if mask_secrets(encoded) != encoded:
            raise CommandError("정책에 비밀정보 형태의 문자열이 있어 백업·변경을 중단합니다.")
        try:
            backup.parent.mkdir(parents=True, exist_ok=True)
            with backup.open("x", encoding="utf-8") as stream:
                stream.write(encoded)
        except OSError as exc:
            raise CommandError("새 백업 파일을 만들 수 없어 변경하지 않았습니다.") from exc

        if change_setting:
            set_setting(SETTING_KEY, VERDICT_DEFINITIONS)
        for prompt, change in zip(targets, plan["prompts"], strict=True):
            # Preserve manual user templates, schema, notes and all prior version contents.
            replacement = PromptTemplate.objects.create(
                key=prompt.key,
                version=change["to"],
                name=prompt.name,
                description=prompt.description,
                system_prompt=COMMON_SYSTEM,
                user_prompt_template=prompt.user_prompt_template,
                output_schema=prompt.output_schema,
                notes=f"B5A 판정·근거 정책 정합성 (이전 v{prompt.version})",
                updated_by=prompt.updated_by,
            )
            replacement.activate()
        self.stdout.write(json.dumps({"applied": True, **plan}, ensure_ascii=False))
