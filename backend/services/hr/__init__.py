"""HR 시스템 어댑터.

플랫폼이 HR(조직·인력) 데이터를 읽는 **유일한 통로**다. `org`, `person`,
`level`, `sched` 같은 HR 원천 테이블을 이 계층 밖에서 직접 조회하지 않는다.

왜 계층을 두는가
---------------
People DB는 **실제 HR 시스템의 대역**이다. Workday API는 결제한 기업 고객만 쓸 수
있어 붙일 수 없고, 조직도·인력은 원래 HR 안에 있는 것이라 Workday 문서를 참고해
같은 모양의 DB를 만들어 대신 쓴다. "나중에 진짜로 교체할 임시물"이 아니라 이
목업이 계속 HR 자리를 지킨다.

그렇다면 코드도 HR을 **남의 시스템처럼** 다뤄야 하는데, 1차 구현에서 `mock_hr`
스키마 분리를 생략하고 `public`에 넣으면서 코어 쿼리가 HR 테이블을 우리 것처럼
직접 JOIN하게 됐다. 설계 의도와 코드가 어긋난 상태였다.

그래서 이 계층은 **커서를 받지 않는다.** 호출자의 트랜잭션에 얹히지 않고 스스로
연결을 열어 평범한 dict를 돌려준다. Drive·Jira의 `apps/connectors/clients.py`와
같은 모양이다. HR 원천 테이블은 애플리케이션에서 읽기 전용이라 이렇게 분리할 수 있다.

테넌트는 여기 없다
-----------------
HR은 **회사**의 인사 시스템이지만, 우리 플랫폼을 쓰는 단위는 회사 전체가 아니라
그 안의 **팀**이다. 그래서 경계는 플랫폼 쪽(`team`/`team_member`)이 갖고, 이
계층은 "주어진 조직·사람을 읽어준다"까지만 한다.

이 계층에 회사 스코프를 넣었다가 걷어낸 이력이 있다. 조직도에서 경계를 유도하면
팀장은 회사 전체를 보게 되고(과다) 팀원은 자기 그룹을 알 수 없다(불가). 자세한
배경은 `docs/3_설계/HR_어댑터와_테넌트_경계.md`.
"""

from .mock_db import (
    count_orgs,
    discover_person_by_email,
    get_person,
    is_available,
    list_absences,
    list_capacity_profiles,
    list_orgs,
    list_person_skills,
    list_persons,
    lookup_orgs,
    lookup_person_ids_by_external_email,
    lookup_persons,
    subtree_org_ids,
)

__all__ = [
    "count_orgs",
    "discover_person_by_email",
    "get_person",
    "is_available",
    "list_absences",
    "list_capacity_profiles",
    "list_orgs",
    "list_person_skills",
    "list_persons",
    "lookup_orgs",
    "lookup_person_ids_by_external_email",
    "lookup_persons",
    "subtree_org_ids",
]
