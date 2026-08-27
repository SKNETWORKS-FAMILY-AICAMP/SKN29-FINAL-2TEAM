"""`python manage.py skill_validation_worker` — 스킬 등록 검증 상시 워커.

정본: docs/설계 및 구현/3_중간발표 이후/작업기록/Juyeon_Agents_Description/
      03_스킬_검증_등록_설계.md §10 ("워커 배포와 운영")

**웹 요청 스레드에서 돌리지 않는다.** 웹 프로세스가 재시작되거나(배포) 요청이
끝나도 검증은 계속돼야 하므로 별도 상시 프로세스로 실행한다. 이 워커 프로세스
내부의 제한된 `ThreadPoolExecutor`는 서로 다른 계정의 job만 병렬 처리한다.

`backend/db/skill_jobs.py`의 `SkillRegistrationJobRepository.claim_next()`가
`FOR UPDATE SKIP LOCKED`로 동시에 여러 워커가 떠 있어도 같은 job을 두 번
집지 않게 한다 — 이 커맨드 자체는 몇 개를 띄우든 안전하다(§10 "초기 운영은
워커 1개로 시작하고 부하가 늘면 동일 서비스를 수평 확장한다").
"""

from __future__ import annotations

import logging
import signal
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait

from django.conf import settings
from django.core.management.base import BaseCommand

from backend.db.skill_jobs import (
    STAGE_CHECKING,
    STAGE_PREPARING_TESTS,
    STAGE_PUBLISHING,
    STAGE_TESTING,
    SkillJobLeaseLost,
    SkillRegistrationJobRepository,
)
from backend.db.skill_operations import SkillWorkerHeartbeatRepository
from services.agent_runtime.skills.registration import (
    CheckingFailure,
    run_checking,
    run_preparing_tests,
    run_publishing,
    run_testing,
)

logger = logging.getLogger(__name__)

#: 폴링 간격 기본값. `IndexingProgress.tsx`의 프런트 폴링과 별개다 — 이건
#: 워커가 "새 QUEUED job이 있는가"를 DB에 묻는 간격이다. 질의 자체가
#: 인덱스 하나(`ix_skill_registration_job_queue`)로 가벼워서(§DB 마이그레이션
#: 파일 참고) 짧게 잡아도 부담이 적다.
DEFAULT_POLL_SECONDS = 3
#: lease 길이. 이 값보다 오래 아무 heartbeat도 없으면 다른 워커가 이 job을
#: 회수한다(§10 "작업 가져오기와 복구"). 지금 단계(형식 검사 + 즉시 등록)는
#: 수 초면 끝나므로 넉넉히 잡는다 — §8의 실제 트리거 테스트가 붙어 실행
#: 시간이 길어지면(최대 5분, §8.12) 이 기본값도 같이 늘려야 한다.
DEFAULT_LEASE_SECONDS = 120
#: 한 job을 처리하는 동안 이 간격마다 heartbeat를 갱신한다. `DEFAULT_LEASE_SECONDS`
#: 보다 충분히 짧아야, heartbeat 한 번을 놓쳐도 lease가 만료되기 전에 다음
#: 기회가 있다.
HEARTBEAT_INTERVAL_SECONDS = 30


class _StopRequested(Exception):
    """SIGTERM/SIGINT를 받았다 — 새 job을 더 가져오지 않고 종료한다."""


class Command(BaseCommand):
    help = "스킬 등록 검증 job을 처리하는 상시 워커. Ctrl+C 또는 SIGTERM으로 정상 종료한다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--poll-interval",
            type=float,
            default=DEFAULT_POLL_SECONDS,
            help=f"새 job이 없을 때 다시 확인할 간격(초). 기본 {DEFAULT_POLL_SECONDS}",
        )
        parser.add_argument(
            "--lease-seconds",
            type=int,
            default=DEFAULT_LEASE_SECONDS,
            help=f"job을 붙잡는 lease 길이(초). 기본 {DEFAULT_LEASE_SECONDS}",
        )
        parser.add_argument(
            "--concurrency",
            type=int,
            default=settings.SKILL_VALIDATION_WORKER_CONCURRENCY,
            help="한 워커 프로세스 안에서 동시에 처리할 job 수",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="큐에 있는 job을 전부 처리하면(더 없으면) 종료한다 — 테스트·수동 실행용.",
        )

    def handle(self, *args, **options):
        poll_interval: float = options["poll_interval"]
        lease_seconds: int = options["lease_seconds"]
        run_once: bool = options["once"]
        concurrency = max(1, int(options.get("concurrency", settings.SKILL_VALIDATION_WORKER_CONCURRENCY)))

        # 이 프로세스(+PID)가 붙잡은 job을 다른 워커·재실행과 구분하는 값.
        worker_id = f"{uuid.uuid4().hex[:12]}"

        stop = {"requested": False}

        def _request_stop(signum, _frame):  # noqa: ARG001
            logger.info("skill_validation_worker: 종료 신호(%s) 받음 — 새 job은 더 안 가져온다", signum)
            stop["requested"] = True

        signal.signal(signal.SIGTERM, _request_stop)
        signal.signal(signal.SIGINT, _request_stop)

        self.stdout.write(self.style.SUCCESS(
            f"skill_validation_worker 시작 (worker_id={worker_id}, concurrency={concurrency})"
        ))
        self._touch_worker(worker_id)

        active: set[Future[None]] = set()
        with ThreadPoolExecutor(
            max_workers=concurrency,
            thread_name_prefix="skill-validation-job",
        ) as executor:
            while True:
                self._touch_worker(worker_id)

                completed = {future for future in active if future.done()}
                active -= completed
                for future in completed:
                    try:
                        future.result()
                    except Exception:  # noqa: BLE001 — 슬롯 하나의 예외가 워커 전체를 끝내면 안 된다.
                        logger.exception("skill_validation_worker: 실행 슬롯에서 예상 못 한 오류")

                if stop["requested"]:
                    if not active:
                        break
                    wait(active, timeout=poll_interval, return_when=FIRST_COMPLETED)
                    continue

                queue_empty = False
                while len(active) < concurrency:
                    job = SkillRegistrationJobRepository.claim_next(
                        lease_owner=worker_id, lease_seconds=lease_seconds
                    )
                    if job is None:
                        queue_empty = True
                        break
                    active.add(executor.submit(
                        self._process,
                        job,
                        lease_owner=worker_id,
                        lease_seconds=lease_seconds,
                    ))

                if run_once and queue_empty and not active:
                    break
                if active:
                    wait(active, timeout=poll_interval, return_when=FIRST_COMPLETED)
                else:
                    time.sleep(poll_interval)

        self.stdout.write(self.style.SUCCESS("skill_validation_worker 종료"))

    def _process(self, job: dict, *, lease_owner: str, lease_seconds: int) -> None:
        from services.agent_runtime.skills.evaluation.config import EVAL_JOB_TIMEOUT_SECONDS

        deadline = time.monotonic() + EVAL_JOB_TIMEOUT_SECONDS
        job["_eval_deadline"] = deadline
        job_id = job["job_id"]
        skill_name = job["skill_name"]
        heartbeat_stop = threading.Event()
        lease_lost = threading.Event()
        heartbeat_interval = min(
            HEARTBEAT_INTERVAL_SECONDS,
            max(1.0, lease_seconds / 3),
        )

        def heartbeat_loop() -> None:
            """LLM 호출 중에도 lease를 유지한다.

            평가 한 단계가 2분보다 길 수 있어 단계 사이에서만 heartbeat를
            갱신하면 다른 워커가 같은 RUNNING job을 회수한다. 별도 daemon
            스레드는 DB heartbeat만 담당하고 평가/Store에는 접근하지 않는다.
            """

            while not heartbeat_stop.wait(heartbeat_interval):
                try:
                    self._touch_worker(lease_owner)
                    SkillRegistrationJobRepository.heartbeat(
                        job_id, lease_owner=lease_owner, lease_seconds=lease_seconds
                    )
                except SkillJobLeaseLost:
                    lease_lost.set()
                    return
                except Exception:  # noqa: BLE001 - 다음 주기에 다시 시도한다.
                    logger.exception("skill_validation_worker: job %s heartbeat 실패", job_id)

        heartbeat_thread = threading.Thread(
            target=heartbeat_loop,
            name=f"skill-heartbeat-{job_id}",
            daemon=True,
        )
        heartbeat_thread.start()

        def ensure_lease() -> None:
            # RUNNING 취소 시 request_cancel()이 상태를 CANCEL_REQUESTED로
            # 바꾸므로 heartbeat/update_progress의 RUNNING 조건은 즉시
            # 실패한다. lease 상실로만 처리하면 아무 워커도 다시 집지 않는
            # CANCEL_REQUESTED가 영원히 남는다. lease_lost보다 취소를 먼저
            # 확인해 이 워커가 CANCELED로 닫는다.
            if SkillRegistrationJobRepository.is_cancel_requested(job_id):
                SkillRegistrationJobRepository.mark_canceled(
                    job_id, lease_owner=lease_owner
                )
                raise _StopRequested
            if lease_lost.is_set():
                raise _StopRequested

        def report(message: str, current: int | None = None, total: int | None = None) -> None:
            ensure_lease()
            try:
                SkillRegistrationJobRepository.update_progress(
                    job_id,
                    lease_owner=lease_owner,
                    message=message,
                    current=current,
                    total=total,
                )
            except SkillJobLeaseLost:
                # 취소와 update 사이의 짧은 race도 같은 방식으로 닫는다.
                ensure_lease()
                raise

        def advance(stage: str, message: str) -> None:
            ensure_lease()
            if SkillRegistrationJobRepository.is_cancel_requested(job_id):
                SkillRegistrationJobRepository.mark_canceled(job_id, lease_owner=lease_owner)
                raise _StopRequested
            SkillRegistrationJobRepository.advance_stage(job_id, stage, lease_owner=lease_owner)
            report(message)

        try:
            self.stdout.write(f"[{job_id}] {skill_name} 검증 시작 ({job['operation']})")

            advance(STAGE_CHECKING, "스킬 이름과 설명의 기본 형식을 확인하고 있어요.")
            run_checking(job)
            report("기본 형식과 같은 이름의 스킬이 있는지 확인했어요.")

            advance(STAGE_PREPARING_TESTS, "검증에 사용할 상황을 준비하고 있어요.")
            run_preparing_tests(job, progress=report)
            # `run_preparing_tests()`가 DB에 `test_case_set`/`eval_suite_version`
            # 등을 써 넣는다(§8.9) — 맨 처음 `claim_next()`로 받은 `job`은 그 전
            # 스냅샷이라 그 필드들이 비어 있다. 다시 읽지 않으면 `run_testing()`
            # 이 "질문이 준비 안 됐다"고 오판한다(실제로 겪은 버그).
            job = SkillRegistrationJobRepository.get(job_id)
            job["_eval_deadline"] = deadline

            advance(STAGE_TESTING, "준비한 상황에서 스킬을 반복해서 확인하고 있어요.")
            run_testing(job, progress=report)

            advance(STAGE_PUBLISHING, "검증을 통과한 내용을 개인 스킬로 저장하고 있어요.")
            run_publishing(job)

            ensure_lease()
            SkillRegistrationJobRepository.mark_succeeded(job_id, lease_owner=lease_owner)
            self.stdout.write(self.style.SUCCESS(f"[{job_id}] {skill_name} 등록 완료"))

        except CheckingFailure as exc:
            try:
                ensure_lease()
                SkillRegistrationJobRepository.mark_failed(
                    job_id,
                    lease_owner=lease_owner,
                    failure_code=exc.code,
                    failure_summary=exc.summary,
                    failure_details=exc.details,
                )
            except (SkillJobLeaseLost, _StopRequested):
                self.stdout.write(f"[{job_id}] {skill_name} lease 상실로 실패 결과를 저장하지 않았습니다.")
                return
            self.stdout.write(self.style.WARNING(f"[{job_id}] {skill_name} 검증 실패: {exc.code} — {exc.summary}"))

        except _StopRequested:
            # 취소됐거나(mark_canceled를 이미 불렀다) lease를 잃었다(다른 워커가
            # 이미 가져갔다 — 여기서 더 쓰면 그 워커의 진행을 덮어쓴다). 어느
            # 쪽이든 이 job은 더 건드리지 않고 다음 루프로 넘어간다.
            self.stdout.write(f"[{job_id}] {skill_name} 처리를 멈췄습니다(취소 또는 lease 상실).")

        except Exception as exc:  # noqa: BLE001 — 예상 못 한 오류도 job을 QUEUED에 영원히 묶어두지 않는다.
            logger.exception("skill_validation_worker: job %s 처리 중 예상 못 한 오류", job_id)
            try:
                SkillRegistrationJobRepository.mark_failed(
                    job_id,
                    lease_owner=lease_owner,
                    failure_code="WORKER_INTERNAL_ERROR",
                    failure_summary="검증 중 내부 오류가 발생했습니다. 다시 시도해 주세요.",
                    failure_details={"error": str(exc)},
                )
            except SkillJobLeaseLost:
                pass
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=2)

    @staticmethod
    def _touch_worker(worker_id: str) -> None:
        """운영 관측 장애가 실제 검증 처리를 중단시키지는 않게 한다."""

        try:
            SkillWorkerHeartbeatRepository.touch(worker_id)
        except Exception:  # noqa: BLE001 - 다음 heartbeat에서 복구를 재시도한다.
            logger.exception("skill_validation_worker: worker heartbeat 저장 실패")
