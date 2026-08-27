"""개발 환경에서 임의의 개인 스킬 질문 생성·의미 검토를 진단한다."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.management.base import CommandError

from services.agent_runtime.skills.evaluation.generator import generate_valid_candidates
from services.agent_runtime.skills.evaluation.semantic_reviewer import review_cases
from services.agent_runtime.skills.service import get_personal_skill


class Command(BaseCommand):
    help = "지정한 개인 스킬의 질문 생성과 의미 검토 결과를 출력한다."

    def add_arguments(self, parser):
        parser.add_argument("--account-id", required=True)
        parser.add_argument("--team-id", required=True)
        parser.add_argument("--skill-name", required=True)

    def handle(self, *args, **options):
        if not settings.SKILL_EVAL_DEBUG_COMMANDS_ENABLED:
            raise CommandError("이 명령은 개발 환경에서만 사용할 수 있습니다.")
        from services.agent_runtime.skills.evaluation.pipeline import _available_tools_for, _other_skills_for

        account_id = options["account_id"]
        team_id = options["team_id"]
        current = get_personal_skill(account_id, options["skill_name"])
        document = {
            "name": current["name"],
            "description": current["description"],
            "body": current["body"],
            "enabled": True,
        }
        available_tools = _available_tools_for(account_id, team_id)
        other_skills = _other_skills_for(account_id)

        positive, negative, author_model = generate_valid_candidates(
            skill_document=document, available_tools=available_tools, other_skills=other_skills
        )
        self.stdout.write(f"author_model={author_model}")
        self.stdout.write(f"positive={len(positive)} negative={len(negative)}")
        for c in positive + negative:
            self.stdout.write(f"  [{c.category}] activate={c.should_activate_candidate} query={c.query!r}")

        reviews, reviewer_model = review_cases(positive + negative, skill_description=document["description"])
        self.stdout.write(f"reviewer_model={reviewer_model}")
        for c, r in zip(positive + negative, reviews, strict=True):
            self.stdout.write(f"overall={r.overall()} query={c.query!r}")
            self.stdout.write(f"  rubrics={json.dumps(r.__dict__, ensure_ascii=False, default=str)}")
