"""§8.7 "플랫폼 고정 probe 관리" — `cases/platform_probes.v1.yaml` 로더.

파일이 하나뿐이라 매 job마다 다시 읽어도 비용이 무시할 만하다 — 캐싱하지
않는다(`services.agent_runtime` 전반의 "호출마다 새로 조립" 관례,
`bootstrap.py` 참고).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .privacy import validate_anonymized_case

_PROBES_PATH = Path(__file__).parent / "cases" / "platform_probes.v1.yaml"


def load_platform_probes() -> tuple[str, list[dict[str, Any]]]:
    """`(dataset_version, probe 목록)`을 돌려준다.

    각 probe는 §8.2 `SkillEvalCase`의 부분집합(생성기 출력과 같은 얕은 dict
    모양)이다 — `suite.py`가 최종 12개로 합칠 때 나머지 필드(`source`,
    `should_activate_candidate=False` 등)를 채워 넣는다.
    """

    raw = yaml.safe_load(_PROBES_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("dataset_version"), str):
        raise ValueError("플랫폼 probe 버전 형식이 올바르지 않습니다.")
    cases = raw.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("플랫폼 probe 사례가 필요합니다.")
    identifiers: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("플랫폼 probe 사례 형식이 올바르지 않습니다.")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in identifiers:
            raise ValueError("플랫폼 probe 식별자는 비어 있지 않고 서로 달라야 합니다.")
        identifiers.add(case_id)
        validate_anonymized_case({**case, "polarity": "negative"})
    return raw["dataset_version"], cases


__all__ = ["load_platform_probes"]
