"""보존 기간이 지난 스킬 검증 데이터 정리."""

from django.conf import settings
from django.core.management.base import BaseCommand

from backend.db.skill_jobs import SkillRegistrationJobRepository
from backend.db.skill_eval import SkillEvalFeedbackRepository


class Command(BaseCommand):
    help = "보존 기간이 지난 스킬 검증 본문·trace를 비식별화하고 실패/취소 기록을 삭제합니다."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="변경 없이 대상 건수만 확인합니다.")

    def handle(self, *args, **options):
        result = SkillRegistrationJobRepository.cleanup_expired(
            succeeded_days=settings.SKILL_VALIDATION_SUCCEEDED_RETENTION_DAYS,
            terminal_days=settings.SKILL_VALIDATION_TERMINAL_RETENTION_DAYS,
            dry_run=options["dry_run"],
        )
        eval_result = SkillEvalFeedbackRepository.cleanup_expired(
            feedback_days=settings.SKILL_EVAL_FEEDBACK_RETENTION_DAYS,
            unapproved_case_days=settings.SKILL_EVAL_UNAPPROVED_CASE_RETENTION_DAYS,
            dry_run=options["dry_run"],
        )
        prefix = "정리 예정" if options["dry_run"] else "정리 완료"
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}: 성공 기록 비식별화 {result['redacted']}건, "
                f"실패·취소 기록 삭제 {result['deleted']}건, 신고 삭제 {eval_result['feedback_deleted']}건, "
                f"미승인 회귀 사례 삭제 {eval_result['case_deleted']}건"
            )
        )
