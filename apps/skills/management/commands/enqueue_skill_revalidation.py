"""개발 환경에서 지정한 개인 스킬의 재검증 작업을 큐에 넣는다."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from services.agent_runtime.skills.registration import SkillRegistrationService
from services.agent_runtime.skills.service import get_personal_skill


class Command(BaseCommand):
    help = "지정한 개인 스킬을 현재 검증 파이프라인으로 다시 검증한다."

    def add_arguments(self, parser):
        parser.add_argument("--account-id", required=True)
        parser.add_argument("--team-id", required=True)
        parser.add_argument("--skill-name", required=True)

    def handle(self, *args, **options):
        if not settings.SKILL_EVAL_DEBUG_COMMANDS_ENABLED:
            raise CommandError("이 명령은 개발 환경에서만 사용할 수 있습니다.")
        current = get_personal_skill(options["account_id"], options["skill_name"])
        result = SkillRegistrationService.enqueue(
            account_id=options["account_id"], team_id=options["team_id"],
            name=current["name"], description=current["description"], body=current["body"],
        )
        self.stdout.write(self.style.SUCCESS(
            f"job_id={result.job['job_id']} created={result.created}"
        ))
