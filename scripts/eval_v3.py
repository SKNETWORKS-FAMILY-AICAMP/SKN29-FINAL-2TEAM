"""PLATFORM_BEHAVIOR_V3 66회 suite를 검증·계획·실행한다."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
V2_FIXTURES = (
    REPO_ROOT
    / "docs"
    / "설계 및 구현"
    / "3_중간발표 이후"
    / "설계"
    / "eval"
    / "v2"
    / "fixtures"
    / "dev"
)
V3_ROOT = (
    REPO_ROOT
    / "docs"
    / "설계 및 구현"
    / "3_중간발표 이후"
    / "설계"
    / "eval"
    / "v3"
)
V3_FIXTURES = V3_ROOT / "fixtures" / "dev"
SUITE_PATH = V3_ROOT / "suite.yaml"
RESULTS_ROOT = REPO_ROOT / "outputs" / "eval-v3-results"
BINDING_ROOT = REPO_ROOT / "outputs" / "eval-v3-fixture-bindings"
ORCHESTRATION_ROOT = REPO_ROOT / "outputs" / "eval-v3-orchestration"
FREEZE_ROOT = REPO_ROOT / "outputs" / "eval-v3-freeze"
CORPUS_ROOT = REPO_ROOT / "tests" / "eval" / "documents" / "pdf"
GOLDEN_ROOT = REPO_ROOT / "tests" / "eval" / "golden"


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"YAML 객체가 필요합니다: {path}")
    return payload


def _suite() -> dict[str, Any]:
    return _load_yaml(SUITE_PATH)


def _variants(suite: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cohort in suite.get("cohorts") or []:
        cohort_id = str(cohort.get("id") or "")
        variants = cohort.get("variants") or []
        if len(variants) != int(cohort.get("expected_variants", -1)):
            raise ValueError(f"{cohort_id} variant 수가 expected_variants와 다릅니다.")
        for variant in variants:
            if not isinstance(variant, dict):
                raise ValueError(f"{cohort_id} variant가 객체가 아닙니다.")
            rows.append({**variant, "cohort": cohort_id})
    return rows


def _golden_query_count() -> int:
    paths = [GOLDEN_ROOT / "retrieval.json", *sorted(GOLDEN_ROOT.glob("queries_*.json"))]
    total = 0
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        queries = payload.get("queries") or []
        if not isinstance(queries, list):
            raise ValueError(f"queries 목록이 아닙니다: {path}")
        total += len(queries)
    return total


def _git_state() -> dict[str, Any]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    tracked_status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.splitlines()
    all_status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.splitlines()
    return {
        "commit": commit,
        "dirty": bool(tracked_status),
        "tracked_changed_path_count": len(tracked_status),
        "untracked_path_count": len(all_status) - len(tracked_status),
    }


def _env_value(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    env_path = REPO_ROOT / ".env"
    if not env_path.is_file():
        return ""
    return next(
        (
            line.split("=", 1)[1].strip()
            for line in env_path.read_text(encoding="utf-8").splitlines()
            if line.startswith(f"{name}=")
        ),
        "",
    )


def _configure_local_database_url() -> None:
    database_url = _env_value("DATABASE_URL")
    if sys.platform == "win32" and urlparse(database_url).hostname == "db":
        os.environ["DATABASE_URL"] = database_url.replace("@db:", "@127.0.0.1:")


def _indexing_preflight() -> list[str]:
    required = ("RUNPOD_API_KEY", "RUNPOD_ENDPOINT_ID", "PUBLIC_BACKEND_BASE_URL")
    return [name for name in required if not _env_value(name)]


def validate_setup() -> dict[str, Any]:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from services.evaluation.v2_fixtures import validate_fixture_tree

    suite = _suite()
    if suite.get("protocol") != "PLATFORM_BEHAVIOR_V3":
        raise ValueError("suite protocol이 PLATFORM_BEHAVIOR_V3가 아닙니다.")
    variants = _variants(suite)
    ids = [str(row.get("id") or "") for row in variants]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("variant id가 비었거나 중복됐습니다.")
    expected = suite.get("expected") or {}
    repetitions = int(suite.get("repetitions", 0))
    if len(variants) != int(expected.get("variants", -1)):
        raise ValueError("전체 variant 수가 suite expected와 다릅니다.")
    if len(variants) * repetitions != int(expected.get("official_runs", -1)):
        raise ValueError("공식 실행 수가 variant × repetitions와 다릅니다.")

    legacy = [row for row in variants if row["cohort"] != "DOCUMENT_SEARCH_DELTA"]
    delta = [row for row in variants if row["cohort"] == "DOCUMENT_SEARCH_DELTA"]
    if len(legacy) != int(expected.get("legacy_variants", -1)):
        raise ValueError("legacy variant 수가 잘못됐습니다.")
    if len(delta) != int(expected.get("delta_variants", -1)):
        raise ValueError("delta variant 수가 잘못됐습니다.")

    for row in variants:
        runner = REPO_ROOT / str(row.get("runner") or "")
        if not runner.is_file():
            raise FileNotFoundError(f"runner가 없습니다: {runner}")
    delta_packages = validate_fixture_tree(V3_FIXTURES, repo_root=REPO_ROOT)
    delta_fixture_ids = {item["fixture_id"] for item in delta_packages}
    if delta_fixture_ids != {str(row["fixture_id"]) for row in delta}:
        raise ValueError("suite의 delta fixture와 실제 package가 다릅니다.")
    legacy_packages = validate_fixture_tree(V2_FIXTURES, repo_root=REPO_ROOT)

    corpus_count = len(list(CORPUS_ROOT.rglob("*.pdf")))
    query_count = _golden_query_count()
    if corpus_count != 101:
        raise ValueError(f"평가 PDF는 101개여야 합니다: actual={corpus_count}")
    if query_count != 143:
        raise ValueError(f"현재 golden 질의는 143개여야 합니다: actual={query_count}")
    return {
        "status": "READY",
        "protocol": suite["protocol"],
        "suite_version": suite["suite_version"],
        "variants": len(variants),
        "legacy_variants": len(legacy),
        "delta_variants": len(delta),
        "repetitions": repetitions,
        "official_runs": len(variants) * repetitions,
        "v2_fixture_packages": len(legacy_packages),
        "v3_delta_fixture_packages": len(delta_packages),
        "corpus_pdf_count": corpus_count,
        "golden_query_count_reference_only": query_count,
        "git": _git_state(),
    }


def _selected_variants(
    suite: dict[str, Any], *, variant_id: str | None, cohort: str
) -> list[dict[str, Any]]:
    variants = _variants(suite)
    if variant_id:
        selected = [row for row in variants if row["id"] == variant_id]
        if not selected:
            raise ValueError(f"모르는 variant입니다: {variant_id}")
        return selected
    cohort_map = {
        "all": None,
        "core": "V2_CORE_REGRESSION",
        "expansion": "V2_EXPANSION_REGRESSION",
        "delta": "DOCUMENT_SEARCH_DELTA",
    }
    wanted = cohort_map[cohort]
    return variants if wanted is None else [row for row in variants if row["cohort"] == wanted]


def _command(
    row: dict[str, Any], *, account_id: str, agent_id: str, agent_version_id: str
) -> list[str]:
    command = [sys.executable, str(REPO_ROOT / row["runner"]), *[str(v) for v in row.get("args", [])]]
    if row["cohort"] == "DOCUMENT_SEARCH_DELTA":
        fixture_dir = V3_FIXTURES / row["fixture_id"]
        binding = BINDING_ROOT / f"{row['fixture_id']}.json"
        command.extend(["--fixture-dir", str(fixture_dir), "--binding", str(binding)])
    command.extend(
        [
            "--account-id",
            account_id,
            "--agent-id",
            agent_id,
            "--agent-version-id",
            agent_version_id,
            "--output-root",
            str(RESULTS_ROOT),
        ]
    )
    return command


def build_plan(
    *,
    variant_id: str | None,
    cohort: str,
    repeats: int,
    account_id: str,
    agent_id: str,
    agent_version_id: str,
) -> dict[str, Any]:
    if repeats < 1 or repeats > 3:
        raise ValueError("repeats는 1~3이어야 합니다.")
    selected = _selected_variants(_suite(), variant_id=variant_id, cohort=cohort)
    rows: list[dict[str, Any]] = []
    for variant in selected:
        for repeat in range(1, repeats + 1):
            rows.append(
                {
                    "ordinal": len(rows) + 1,
                    "cohort": variant["cohort"],
                    "variant_id": variant["id"],
                    "fixture_id": variant["fixture_id"],
                    "repeat": repeat,
                    "command": _command(
                        variant,
                        account_id=account_id,
                        agent_id=agent_id,
                        agent_version_id=agent_version_id,
                    ),
                }
            )
    return {
        "protocol": "PLATFORM_BEHAVIOR_V3",
        "candidate_id": f"{agent_id}/{agent_version_id}",
        "account_id": account_id,
        "git": _git_state(),
        "planned_runs": len(rows),
        "runs": rows,
    }


def _check_index(account_id: str) -> dict[str, Any]:
    _configure_local_database_url()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    import django

    django.setup()
    from backend.db.document_pipeline import PersonalDocumentRepository

    expected = {path.name for path in CORPUS_ROOT.rglob("*.pdf")}
    try:
        rows = PersonalDocumentRepository.list_for_account(account_id)
    except Exception as exc:
        return {
            "status": "BLOCKED_CONNECTION",
            "account_id": account_id,
            "error_type": type(exc).__name__,
            "action": "평가 DB를 실행하고 로컬 실행이면 DATABASE_URL의 db host를 127.0.0.1로 지정하세요.",
        }
    ready_names = {
        str(row.get("file_name"))
        for row in rows
        if row.get("search_ready") is True or row.get("index_status") == "READY"
    }
    missing = sorted(expected - ready_names)
    return {
        "status": "READY" if not missing else "NOT_READY",
        "account_id": account_id,
        "expected_pdf_count": len(expected),
        "ready_expected_pdf_count": len(expected & ready_names),
        "missing_count": len(missing),
        "missing": missing,
    }


def _provision_delta(account_id: str, *, resume: bool) -> int:
    missing_settings = _indexing_preflight()
    if missing_settings:
        print(
            json.dumps(
                {
                    "status": "BLOCKED_CONFIGURATION",
                    "missing_settings": missing_settings,
                    "action": "RunPod worker가 평가 원문을 받을 수 있는 공개 backend URL까지 설정한 뒤 다시 실행하세요.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    failures: list[dict[str, Any]] = []
    delta = _selected_variants(_suite(), variant_id=None, cohort="delta")
    for row in delta:
        fixture_dir = V3_FIXTURES / row["fixture_id"]
        binding = BINDING_ROOT / f"{row['fixture_id']}.json"
        action = "resume" if resume or binding.exists() else "provision"
        command = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "eval_v2_documents.py"),
            action,
            "--account-id",
            account_id,
            "--fixture-dir",
            str(fixture_dir),
            "--binding",
            str(binding),
        ]
        completed = subprocess.run(command, cwd=REPO_ROOT, check=False)
        if completed.returncode != 0:
            failures.append({"variant_id": row["id"], "returncode": completed.returncode})
    print(json.dumps({"status": "READY" if not failures else "FAILED", "failures": failures}, ensure_ascii=False, indent=2))
    return 0 if not failures else 2


def _provision_corpus(account_id: str, *, limit: int | None) -> int:
    missing_settings = _indexing_preflight()
    if missing_settings:
        print(
            json.dumps(
                {
                    "status": "BLOCKED_CONFIGURATION",
                    "missing_settings": missing_settings,
                    "action": "외부 worker가 접근 가능한 공개 backend URL을 설정한 뒤 다시 실행하세요.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    if limit is not None and limit < 1:
        raise ValueError("limit은 1 이상이어야 합니다.")

    _configure_local_database_url()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    import django

    django.setup()
    from backend.db.document_pipeline import PersonalDocumentRepository
    from backend.db.repositories import DocumentRepository
    from backend.services import storage
    from services.document_intake import LONG_PROMOTE_WAIT_SECONDS, promote_to_searchable

    current_rows = PersonalDocumentRepository.list_for_account(account_id)
    by_name: dict[str, list[dict[str, Any]]] = {}
    for row in current_rows:
        by_name.setdefault(str(row.get("file_name")), []).append(row)

    processed = 0
    results: list[dict[str, Any]] = []
    for source_path in sorted(CORPUS_ROOT.rglob("*.pdf")):
        candidates = by_name.get(source_path.name, [])
        ready = next(
            (
                row
                for row in candidates
                if row.get("search_ready") is True or row.get("index_status") == "READY"
            ),
            None,
        )
        if ready is not None:
            results.append({"file_name": source_path.name, "status": "ALREADY_READY", "doc_id": ready["doc_id"]})
            continue
        if limit is not None and processed >= limit:
            continue

        document = candidates[0] if candidates else None
        if document is None:
            data = source_path.read_bytes()
            doc_id = PersonalDocumentRepository.create(
                account_id=account_id,
                file_name=source_path.name,
                mime_type="application/pdf",
            )
            key = storage.build_personal_key(
                account_id=account_id,
                doc_id=doc_id,
                mime_type="application/pdf",
            )
            content_hash = storage.save(key, data)
            DocumentRepository.mark_stored(
                doc_id=doc_id,
                storage_key=key,
                content_hash=content_hash,
                revision=content_hash.removeprefix("sha256:")[:16],
            )
        else:
            doc_id = str(document["doc_id"])
            if not document.get("storage_key"):
                data = source_path.read_bytes()
                key = storage.build_personal_key(
                    account_id=account_id,
                    doc_id=doc_id,
                    mime_type="application/pdf",
                )
                content_hash = storage.save(key, data)
                DocumentRepository.mark_stored(
                    doc_id=doc_id,
                    storage_key=key,
                    content_hash=content_hash,
                    revision=content_hash.removeprefix("sha256:")[:16],
                )
        try:
            outcome = promote_to_searchable(
                account_id=account_id,
                doc_id=doc_id,
                wait_seconds=LONG_PROMOTE_WAIT_SECONDS,
            )
        except Exception as exc:
            outcome = {"ok": False, "detail": type(exc).__name__}
        processed += 1
        results.append(
            {
                "file_name": source_path.name,
                "doc_id": doc_id,
                "status": "READY" if outcome.get("ok") is True else "FAILED",
                "detail": outcome.get("detail"),
            }
        )

    ORCHESTRATION_ROOT.mkdir(parents=True, exist_ok=True)
    report_path = ORCHESTRATION_ROOT / "corpus-provision-latest.json"
    report = {
        "protocol": "PLATFORM_BEHAVIOR_V3",
        "account_id": account_id,
        "processed": processed,
        "ready_or_existing": sum(row["status"] in {"READY", "ALREADY_READY"} for row in results),
        "failed": sum(row["status"] == "FAILED" for row in results),
        "results": results,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "results"} | {"report": str(report_path)}, ensure_ascii=False, indent=2))
    return 0 if report["failed"] == 0 else 2


def _bind_delta(account_id: str) -> int:
    _configure_local_database_url()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    import django

    django.setup()
    from backend.db.document_pipeline import PersonalDocumentRepository

    rows = PersonalDocumentRepository.list_for_account(account_id)
    ready_by_name = {
        str(row.get("file_name")): row
        for row in rows
        if row.get("search_ready") is True or row.get("index_status") == "READY"
    }
    missing: list[str] = []
    written: list[str] = []
    BINDING_ROOT.mkdir(parents=True, exist_ok=True)
    for variant in _selected_variants(_suite(), variant_id=None, cohort="delta"):
        fixture = _load_yaml(V3_FIXTURES / variant["fixture_id"] / "fixture.yaml")
        documents: list[dict[str, Any]] = []
        for source in fixture.get("source_artifacts") or []:
            file_name = Path(source["repo_path"]).name
            row = ready_by_name.get(file_name)
            if row is None:
                missing.append(file_name)
                continue
            documents.append(
                {
                    "source_id": source["source_id"],
                    "repo_path": source["repo_path"],
                    "sha256": source["sha256"],
                    "doc_id": row["doc_id"],
                }
            )
        if len(documents) != len(fixture.get("source_artifacts") or []):
            continue
        binding_path = BINDING_ROOT / f"{fixture['fixture_id']}.json"
        binding_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "fixture_id": fixture["fixture_id"],
                    "fixture_version": fixture["fixture_version"],
                    "account_id": account_id,
                    "status": "READY",
                    "binding_source": "EXISTING_V3_CORPUS",
                    "documents": documents,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        written.append(str(binding_path))
    result = {
        "status": "READY" if not missing else "NOT_READY",
        "binding_count": len(written),
        "missing": sorted(set(missing)),
        "bindings": written,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "READY" else 2


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_snapshot(
    *, account_id: str, team_id: str, agent_id: str, agent_version_id: str
) -> dict[str, Any]:
    _configure_local_database_url()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    import django

    django.setup()
    from backend.db.agent_platform import AgentVersionRepository

    row = AgentVersionRepository.get_definition(
        agent_id=agent_id,
        agent_version_id=agent_version_id,
        account_id=account_id,
        team_id=team_id,
    )
    return {
        "candidate_id": f"{agent_id}/{agent_version_id}",
        "name": row["name"],
        "model": row["model"],
        "reasoning_effort": row["reasoning_effort"],
        "max_iterations": row["max_iterations"],
        "agent_status": row["agent_status"],
        "tool_refs": row["tool_refs"],
    }


def _freeze(
    *, account_id: str, team_id: str, agent_id: str, agent_version_id: str
) -> int:
    setup = validate_setup()
    git = setup["git"]
    if git["dirty"]:
        raise RuntimeError(
            "Candidate 동결은 tracked 변경이 없는 커밋에서만 가능합니다: "
            f"tracked_changes={git['tracked_changed_path_count']}"
        )
    index = _check_index(account_id)
    if index["status"] != "READY":
        raise RuntimeError(
            "Candidate 동결 전 101개 평가 문서가 READY여야 합니다: "
            f"ready={index.get('ready_expected_pdf_count', 0)}/{index.get('expected_pdf_count', 101)}"
        )
    expected_bindings = {
        row["fixture_id"]
        for row in _selected_variants(_suite(), variant_id=None, cohort="delta")
    }
    missing_bindings = sorted(
        fixture_id
        for fixture_id in expected_bindings
        if not (BINDING_ROOT / f"{fixture_id}.json").is_file()
    )
    if missing_bindings:
        raise RuntimeError(f"delta binding이 없습니다: {', '.join(missing_bindings)}")
    candidate = _candidate_snapshot(
        account_id=account_id,
        team_id=team_id,
        agent_id=agent_id,
        agent_version_id=agent_version_id,
    )
    if candidate["agent_status"] != "ACTIVE":
        raise RuntimeError(f"Candidate가 ACTIVE가 아닙니다: {candidate['agent_status']}")

    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "protocol": "PLATFORM_BEHAVIOR_V3",
        "suite_version": setup["suite_version"],
        "created_at": created_at,
        "git": git,
        "candidate": candidate,
        "account_id": account_id,
        "team_id": team_id,
        "index": index,
        "suite_sha256": _sha256(SUITE_PATH),
        "fixture_sha256": {
            path.relative_to(REPO_ROOT).as_posix(): _sha256(path)
            for path in sorted(V3_FIXTURES.rglob("*.yaml"))
        },
        "official_run_count": setup["official_runs"],
        "execution_policy": "SEQUENTIAL_SINGLE_ACCOUNT",
    }
    FREEZE_ROOT.mkdir(parents=True, exist_ok=True)
    output_path = FREEZE_ROOT / f"freeze-{git['commit'][:12]}-{agent_id}-{agent_version_id}.json"
    if output_path.exists():
        raise FileExistsError(f"동결 manifest가 이미 있습니다: {output_path}")
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "FROZEN",
                "manifest": str(output_path),
                "git_commit": git["commit"],
                "candidate_id": candidate["candidate_id"],
                "official_run_count": setup["official_runs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _run_plan(plan: dict[str, Any], *, allow_dirty: bool) -> int:
    if plan["git"]["dirty"] and not allow_dirty:
        raise RuntimeError("공식 V3 실행은 dirty worktree에서 차단됩니다. smoke만 --allow-dirty를 사용하세요.")
    delta_selected = any(row["cohort"] == "DOCUMENT_SEARCH_DELTA" for row in plan["runs"])
    if delta_selected:
        index = _check_index(str(plan["account_id"]))
        if index["status"] != "READY":
            raise RuntimeError(
                "delta 실행 전 평가 계정의 101개 문서 인덱스가 READY여야 합니다: "
                f"ready={index['ready_expected_pdf_count']}/{index['expected_pdf_count']}"
            )

    started = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ORCHESTRATION_ROOT.mkdir(parents=True, exist_ok=True)
    log_path = ORCHESTRATION_ROOT / f"v3-orchestration-{started}.json"
    results: list[dict[str, Any]] = []
    for row in plan["runs"]:
        completed = subprocess.run(row["command"], cwd=REPO_ROOT, check=False)
        results.append({**row, "returncode": completed.returncode})
    payload = {**plan, "results": results}
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"log": str(log_path), "run_count": len(results), "returncodes": [row["returncode"] for row in results]}, ensure_ascii=False, indent=2))
    return 0 if all(row["returncode"] == 0 for row in results) else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="외부 호출 없이 suite·fixture·corpus를 검증")

    check_index = sub.add_parser("check-index", help="평가 계정의 101개 문서 검색 준비 상태 확인")
    check_index.add_argument("--account-id", default="UA002")

    provision = sub.add_parser("provision-delta", help="D01~D06 문서를 평가 계정에 준비")
    provision.add_argument("--account-id", default="UA002")
    provision.add_argument("--resume", action="store_true")

    corpus = sub.add_parser("provision-corpus", help="평가 PDF 101개를 중복 없이 색인")
    corpus.add_argument("--account-id", default="UA002")
    corpus.add_argument("--limit", type=int)

    bind = sub.add_parser("bind-delta", help="기존 101개 corpus에서 D01~D06 binding 생성")
    bind.add_argument("--account-id", default="UA002")

    freeze = sub.add_parser("freeze", help="101개 index·binding·Candidate·commit을 동결")
    freeze.add_argument("--account-id", default="UA002")
    freeze.add_argument("--team-id", default="TM001")
    freeze.add_argument("--agent-id", required=True)
    freeze.add_argument("--agent-version-id", required=True)

    for name in ("plan", "run"):
        command = sub.add_parser(name)
        selector = command.add_mutually_exclusive_group()
        selector.add_argument("--variant")
        selector.add_argument("--cohort", choices=("all", "core", "expansion", "delta"), default="all")
        command.add_argument("--repeats", type=int, default=3)
        command.add_argument("--account-id", default="UA002")
        command.add_argument("--agent-id", required=True)
        command.add_argument("--agent-version-id", required=True)
        if name == "run":
            command.add_argument("--allow-dirty", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "validate":
        print(json.dumps(validate_setup(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "check-index":
        result = _check_index(args.account_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "READY" else 2
    if args.command == "provision-delta":
        validate_setup()
        return _provision_delta(args.account_id, resume=args.resume)
    if args.command == "provision-corpus":
        validate_setup()
        return _provision_corpus(args.account_id, limit=args.limit)
    if args.command == "bind-delta":
        validate_setup()
        return _bind_delta(args.account_id)
    if args.command == "freeze":
        return _freeze(
            account_id=args.account_id,
            team_id=args.team_id,
            agent_id=args.agent_id,
            agent_version_id=args.agent_version_id,
        )
    plan = build_plan(
        variant_id=args.variant,
        cohort=args.cohort,
        repeats=args.repeats,
        account_id=args.account_id,
        agent_id=args.agent_id,
        agent_version_id=args.agent_version_id,
    )
    if args.command == "plan":
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    validate_setup()
    return _run_plan(plan, allow_dirty=args.allow_dirty)


if __name__ == "__main__":
    raise SystemExit(main())
