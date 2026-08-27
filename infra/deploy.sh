#!/usr/bin/env bash
#
# EC2 배포. GitHub Actions(.github/workflows/deploy.yml)가 SSH 로 이걸 실행한다.
#
# 로직을 워크플로 YAML 이 아니라 여기 두는 이유: 저장소에 있으면 리뷰가 되고,
# 서버에 붙어서 손으로 돌려 볼 수도 있다.
#
#   ssh ubuntu@<EC2> 'bash ~/SKN29-Final-2Team/infra/deploy.sh'

set -euo pipefail

REPO="${REPO:-$HOME/SKN29-Final-2Team}"
COMPOSE="-f infra/docker/docker-compose.aws.yml"
MCP_OVERLAY="-f infra/docker/docker-compose.dev-mcp.yml"

cd "$REPO"

echo "::: 1. 코드 갱신"
BEFORE=$(git rev-parse HEAD)
git fetch --prune origin
# ff-only 다. 서버에서 커밋이 생겼으면 조용히 덮지 않고 실패하는 편이 낫다.
git merge --ff-only origin/main
AFTER=$(git rev-parse HEAD)
echo "    $BEFORE -> $AFTER"
git --no-pager log --oneline -1

# MCP 시연 서버가 떠 있으면 오버레이를 파일 목록에 넣는다.
# ⚠ 빼면 compose 가 `skn29-dev-mcp` 를 **이 프로젝트의 고아 컨테이너로 보고
# 경고한다.** 누가 그 경고를 보고 `--remove-orphans` 를 붙이는 순간 시연용
# MCP 서버가 조용히 삭제된다.
MCP_UP=0
FILES="$COMPOSE"
if docker ps --format '{{.Names}}' | grep -q '^skn29-dev-mcp$'; then
  MCP_UP=1
  FILES="$COMPOSE $MCP_OVERLAY"
fi

echo "::: 2. 빌드·기동"
# t3.micro(909MB + swap 2G)라 병렬 빌드가 버겁다. 순차로 돌린다.
#
# `skill-validation-worker` 는 포트를 안 열어서 눈에 안 띄지만 **이 줄에 없으면
# 아예 안 뜬다**(2026-08-27 추가). 빠지면 스킬 등록 요청이
# `skill_registration_job` 에 쌓이기만 하고 화면에는 「검증 중」으로 멈춘 채
# 남는다 — 에러가 아니라 침묵이라 배포로는 안 보인다.
# `web` 과 같은 이미지라 빌드는 캐시로 끝난다.
COMPOSE_PARALLEL_LIMIT=1 docker compose $FILES up -d --build web frontend caddy skill-validation-worker

echo "::: 3. MCP 시연 서버"
# server.py 는 바인드 마운트라 재빌드가 아니라 재생성이면 반영된다.
if [ "$MCP_UP" = 1 ]; then
  docker compose $FILES up -d --force-recreate dev-mcp
  echo "    재기동함"
else
  echo "    안 떠 있어서 건너뜀"
fi

echo "::: 3.5 스키마 확인"
# 코드가 전제하는 컬럼·인덱스가 RDS 에 있는지 **읽기만** 해서 확인한다.
# 적용은 하지 않는다 — .sql 인자를 안 주면 `_apply.py` 는 SELECT 만 돈다.
# 마이그레이션에 DROP·DELETE 가 섞이므로 거는 것은 언제나 사람 손이다.
#
# 왜 필요한가: 4단계 헬스 체크의 `database` 항목은 **연결만** 본다. 그래서
# 「새 컬럼을 읽는 코드 + 그 컬럼이 없는 RDS」가 헬스 체크를 멀쩡히 통과한다.
# 2026-08-18 에 그 상태로 배포돼 채팅이 통째로 막혔고, 2026-08-24 에도 같은
# 순서로 나갔다(그때는 운으로 안 터졌다).
#
# ⚠ 한계: 여기서 걸리면 새 코드는 이미 떠 있다. 이 줄은 사고를 **막지** 못하고
# 조용한 고장을 시끄러운 배포 실패로 바꿀 뿐이다. 그래도 사용자가 먼저
# 발견하는 것보다는 낫다. 막으려면 마이그레이션을 push 전에 넣어야 한다.
#
# set -e 가 걸려 있어 빠진 것이 있으면 여기서 배포가 멈춘다.
docker compose $FILES exec -T web python DB/migrations/_apply.py --check

echo "::: 4. 헬스 체크"
# ⚠ X-Forwarded-Proto 를 붙여야 한다. production 설정의 SECURE_SSL_REDIRECT 가
# 켜져 있어서, 이 헤더 없이 http 로 부르면 301 이 돌아온다(앱이 죽은 게 아니다).
for i in $(seq 1 20); do
  if BODY=$(curl -fsS --max-time 5 -H 'X-Forwarded-Proto: https' \
              http://localhost:8000/api/health/ 2>/dev/null); then
    echo "    $BODY"
    case "$BODY" in
      *'"status": "ok"'*|*'"status":"ok"'*) : ;;
      *) echo "    헬스 응답이 ok 가 아니다"; exit 1 ;;
    esac
    case "$BODY" in
      *'"database"'*'"ok"'*) : ;;
      *) echo "    DB 가 붙지 않았다"; exit 1 ;;
    esac
    break
  fi
  [ "$i" -eq 20 ] && { echo "    20회 시도 후에도 응답 없음"; docker compose $FILES logs --tail 50 web; exit 1; }
  sleep 3
done

echo "::: 5. 정리"
# 29G 디스크에 dangling 이미지가 쌓인다. 배포마다 걷어낸다.
docker image prune -f >/dev/null
echo "    디스크: $(df -h / | awk 'NR==2{print $3" / "$2" ("$5")"}')"

echo "::: 배포 완료"
docker compose $FILES ps --format '    {{.Service}}  {{.Status}}'
