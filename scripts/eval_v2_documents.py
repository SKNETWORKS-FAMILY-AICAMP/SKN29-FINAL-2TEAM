"""V2 fixture의 기존 PDF를 평가 계정에 정확히 provision/status/cleanup한다."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = (
    REPO_ROOT
    / "docs"
    / "설계 및 구현"
    / "3_중간발표 이후"
    / "설계"
    / "eval"
    / "v2"
    / "fixtures"
    / "dev"
    / "S01-DEV-001"
)
DEFAULT_BINDING_ROOT = REPO_ROOT / "outputs" / "eval-v2-fixture-bindings"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("provision", "resume", "status", "cleanup"):
        command = commands.add_parser(name)
        command.add_argument("--account-id", required=True)
        command.add_argument("--fixture-dir", type=Path, default=DEFAULT_FIXTURE)
        command.add_argument("--binding", type=Path)
    return parser


def _binding_path(args: argparse.Namespace, fixture_id: str) -> Path:
    return args.binding or DEFAULT_BINDING_ROOT / f"{fixture_id}.json"


def _write_binding(path: Path, binding: dict[str, Any], *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(binding, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if exclusive:
        with path.open("x", encoding="utf-8", newline="\n") as destination:
            destination.write(text)
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _load_binding(path: Path, *, account_id: str, fixture_id: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("account_id") != account_id or payload.get("fixture_id") != fixture_id:
        raise ValueError("binding의 계정 또는 fixture가 요청과 다릅니다.")
    return payload


def _django_setup() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    import django

    django.setup()


def _provision(
    args: argparse.Namespace,
    fixture: dict[str, Any],
    binding_path: Path,
    *,
    resume: bool = False,
) -> int:
    from backend.db.document_pipeline import PersonalDocumentRepository
    from backend.db.repositories import DocumentRepository
    from backend.services import storage
    from services.document_intake import LONG_PROMOTE_WAIT_SECONDS, promote_to_searchable

    if resume:
        binding = _load_binding(
            binding_path, account_id=args.account_id, fixture_id=fixture["fixture_id"]
        )
        if binding.get("status") == "CLEANED":
            raise ValueError("정리된 binding은 재사용하지 않습니다. 새 binding 경로를 지정하세요.")
        binding["status"] = "PROVISIONING"
        binding["updated_at"] = _utc_now()
        _write_binding(binding_path, binding)
    else:
        binding = {
            "schema_version": 1,
            "fixture_id": fixture["fixture_id"],
            "fixture_version": fixture["fixture_version"],
            "account_id": args.account_id,
            "created_at": _utc_now(),
            "status": "PROVISIONING",
            "documents": [],
        }
        _write_binding(binding_path, binding, exclusive=True)

    for source in fixture["source_artifacts"]:
        entry = next(
            (item for item in binding["documents"] if item["source_id"] == source["source_id"]),
            None,
        )
        if entry is None:
            source_path = REPO_ROOT / source["repo_path"]
            data = source_path.read_bytes()
            doc_id = PersonalDocumentRepository.create(
                account_id=args.account_id,
                file_name=source_path.name,
                mime_type="application/pdf",
            )
            key = storage.build_personal_key(
                account_id=args.account_id,
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
            entry = {
                "source_id": source["source_id"],
                "repo_path": source["repo_path"],
                "sha256": source["sha256"],
                "doc_id": doc_id,
                "storage_key": key,
                "index_result": None,
            }
            binding["documents"].append(entry)
            _write_binding(binding_path, binding)
        if (entry.get("index_result") or {}).get("ok") is True:
            continue
        try:
            result = promote_to_searchable(
                account_id=args.account_id,
                doc_id=entry["doc_id"],
                wait_seconds=LONG_PROMOTE_WAIT_SECONDS,
            )
        except Exception as exc:
            entry["index_result"] = {"ok": False, "error_type": type(exc).__name__}
            binding["status"] = "BLOCKED_CONFIGURATION"
            binding["updated_at"] = _utc_now()
            _write_binding(binding_path, binding)
            print(json.dumps(binding, ensure_ascii=False, indent=2))
            return 2
        entry["index_result"] = result
        _write_binding(binding_path, binding)
        if result.get("ok") is not True:
            binding["status"] = "BLOCKED_INDEXING"
            binding["updated_at"] = _utc_now()
            _write_binding(binding_path, binding)
            print(json.dumps(binding, ensure_ascii=False, indent=2))
            return 2

    binding["status"] = "READY"
    binding["updated_at"] = _utc_now()
    _write_binding(binding_path, binding)
    print(json.dumps(binding, ensure_ascii=False, indent=2))
    return 0


def _status(args: argparse.Namespace, fixture: dict[str, Any], binding_path: Path) -> int:
    from backend.db.document_pipeline import PersonalDocumentRepository

    binding = _load_binding(
        binding_path, account_id=args.account_id, fixture_id=fixture["fixture_id"]
    )
    current = {
        row["doc_id"]: row for row in PersonalDocumentRepository.list_for_account(args.account_id)
    }
    for document in binding["documents"]:
        row = current.get(document["doc_id"])
        document["current"] = (
            {
                "exists": True,
                "file_name": row.get("file_name"),
                "index_status": row.get("index_status"),
                "search_ready": row.get("search_ready"),
            }
            if row
            else {"exists": False}
        )
    print(json.dumps(binding, ensure_ascii=False, indent=2, default=str))
    return 0


def _cleanup(args: argparse.Namespace, fixture: dict[str, Any], binding_path: Path) -> int:
    from backend.db.document_pipeline import PersonalDocumentRepository
    from backend.db.errors import RecordNotFound
    from backend.services import storage

    binding = _load_binding(
        binding_path, account_id=args.account_id, fixture_id=fixture["fixture_id"]
    )
    removed: list[str] = []
    missing: list[str] = []
    for document in binding["documents"]:
        doc_id = document["doc_id"]
        try:
            key = PersonalDocumentRepository.delete(doc_id=doc_id, account_id=args.account_id)
        except RecordNotFound:
            missing.append(doc_id)
            continue
        if key:
            storage.remove(key)
        removed.append(doc_id)
    binding["cleanup"] = {"removed": removed, "already_missing": missing, "at": _utc_now()}
    binding["status"] = "CLEANED"
    _write_binding(binding_path, binding)
    print(json.dumps(binding["cleanup"], ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    import yaml

    from services.evaluation.v2_fixtures import validate_fixture_package

    args = _parser().parse_args(argv)
    validate_fixture_package(args.fixture_dir, repo_root=REPO_ROOT)
    fixture = yaml.safe_load((args.fixture_dir / "fixture.yaml").read_text(encoding="utf-8"))
    binding_path = _binding_path(args, fixture["fixture_id"])
    _django_setup()
    if args.command == "provision":
        return _provision(args, fixture, binding_path)
    if args.command == "resume":
        return _provision(args, fixture, binding_path, resume=True)
    if args.command == "status":
        return _status(args, fixture, binding_path)
    return _cleanup(args, fixture, binding_path)


if __name__ == "__main__":
    raise SystemExit(main())
