"""Agent Eval V2 fixture/gold package의 실행 전 무결성 검사."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml


ALLOWED_ORACLES = {"DETERMINISTIC", "LLM_JUDGE"}


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}는 YAML 객체여야 합니다.")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_fixture_package(package_dir: Path, *, repo_root: Path) -> dict[str, Any]:
    fixture_path = package_dir / "fixture.yaml"
    gold_path = package_dir / "gold.yaml"
    if not fixture_path.is_file() or not gold_path.is_file():
        raise ValueError(f"fixture.yaml과 gold.yaml이 모두 필요합니다: {package_dir}")
    fixture = _load_yaml(fixture_path)
    gold = _load_yaml(gold_path)

    identity = gold.get("gold_identity")
    if not isinstance(identity, dict):
        raise ValueError("gold_identity가 필요합니다.")
    for field in ("fixture_id", "fixture_version", "gold_version"):
        if fixture.get(field) != identity.get(field):
            raise ValueError(f"fixture와 gold의 {field}가 다릅니다.")
    if fixture.get("fixture_id") != package_dir.name:
        raise ValueError("fixture_id가 package 디렉터리 이름과 다릅니다.")

    source_ids: set[str] = set()
    checked_sources: list[dict[str, Any]] = []
    resolved_root = repo_root.resolve()
    for index, source in enumerate(fixture.get("source_artifacts") or []):
        if not isinstance(source, dict):
            raise ValueError(f"source_artifacts[{index}]가 객체가 아닙니다.")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise ValueError(f"source_artifacts[{index}].source_id가 필요합니다.")
        if source_id in source_ids:
            raise ValueError(f"source_id가 중복됐습니다: {source_id}")
        source_ids.add(source_id)
        relative = source.get("repo_path")
        if not isinstance(relative, str) or not relative:
            raise ValueError(f"{source_id}.repo_path가 필요합니다.")
        source_path = (repo_root / relative).resolve()
        if source_path != resolved_root and resolved_root not in source_path.parents:
            raise ValueError(f"{source_id}.repo_path가 저장소 밖을 가리킵니다.")
        if not source_path.is_file():
            raise ValueError(f"{source_id} source 파일이 없습니다: {relative}")
        expected_hash = source.get("sha256")
        actual_hash = _sha256(source_path)
        if expected_hash != actual_hash:
            raise ValueError(f"{source_id} SHA-256이 다릅니다.")
        checked_sources.append({"source_id": source_id, "sha256": actual_hash})

    facts = (gold.get("truth_catalog") or {}).get("facts") or []
    fact_ids = {item.get("fact_id") for item in facts if isinstance(item, dict)}
    relations = (gold.get("truth_catalog") or {}).get("relations") or []
    relation_ids = {item.get("relation_id") for item in relations if isinstance(item, dict)}
    known_gold_refs = fact_ids | relation_ids
    for fact in facts:
        for ref in fact.get("evidence_refs") or []:
            source_id = str(ref).split(":", 1)[0]
            if source_id not in source_ids:
                raise ValueError(f"{fact.get('fact_id')}가 모르는 source를 참조합니다: {ref}")
    for conclusion in gold.get("required_conclusions") or []:
        unknown = set(conclusion.get("supported_by") or []) - known_gold_refs
        if unknown:
            raise ValueError(
                f"{conclusion.get('conclusion_id')}의 supported_by가 잘못됐습니다: {sorted(unknown)}"
            )

    criterion_ids: set[str] = set()
    for index, binding in enumerate(gold.get("oracle_bindings") or []):
        criterion = binding.get("criterion") if isinstance(binding, dict) else None
        if not isinstance(criterion, str) or not criterion:
            raise ValueError(f"oracle_bindings[{index}].criterion이 필요합니다.")
        if criterion in criterion_ids:
            raise ValueError(f"oracle criterion이 중복됐습니다: {criterion}")
        criterion_ids.add(criterion)
        oracle = binding.get("authoritative_oracle")
        if oracle not in ALLOWED_ORACLES:
            raise ValueError(f"{criterion}.authoritative_oracle이 잘못됐습니다.")
        if oracle == "LLM_JUDGE" and binding.get("scorer_identity") != "gpt-5.6-sol":
            raise ValueError(f"{criterion}의 Judge는 gpt-5.6-sol이어야 합니다.")

    return {
        "fixture_id": fixture["fixture_id"],
        "fixture_version": fixture["fixture_version"],
        "gold_version": fixture["gold_version"],
        "source_count": len(checked_sources),
        "oracle_count": len(criterion_ids),
        "sources": checked_sources,
    }


def validate_fixture_tree(fixtures_root: Path, *, repo_root: Path) -> list[dict[str, Any]]:
    packages = sorted(path for path in fixtures_root.iterdir() if path.is_dir())
    return [validate_fixture_package(path, repo_root=repo_root) for path in packages]


__all__ = ["validate_fixture_package", "validate_fixture_tree"]
