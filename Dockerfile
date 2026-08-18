FROM python:3.13-slim

# 배포 파이프라인이 `docker build --build-arg GIT_COMMIT_SHA=$(git rev-parse HEAD)`로
# 채운다 — 안 넘기면 빈 문자열이고, config/settings/base.py가 그걸 None으로
# 정규화한다(2026-08-14, agent_run.runtime_profile_version). 이 저장소엔 아직
# 그렇게 자동으로 채워주는 CI가 없다 — 배포 스크립트 쪽에서 이 build-arg를
# 넘겨야 실제로 값이 들어간다.
ARG GIT_COMMIT_SHA=""
ENV RUNTIME_PROFILE_VERSION=${GIT_COMMIT_SHA}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/production.txt

COPY . .

RUN useradd --create-home appuser && chown -R appuser:appuser /app

# 문서 저장소. 이미지 안에 미리 만들어 둬야 한다 — Docker는 명명 볼륨을 처음
# 붙일 때 이미지의 같은 경로에서 소유권을 복사하는데, 경로가 없으면 root 소유로
# 만들어 버려서 appuser가 쓸 수 없다.
RUN mkdir -p /var/lib/halil/documents && chown -R appuser:appuser /var/lib/halil

USER appuser

# ⚠ `--timeout` 을 빼면 gunicorn 기본값이 **30초**다. 채팅 한 턴은 문서 승격
# (RunPod 파싱·임베딩)이 걸리면 몇 분이 걸려서, 스트리밍 중인 워커가 그대로
# SIGKILL 된다 — 브라우저에는 `ERR_HTTP2_PROTOCOL_ERROR` 와 「요청을 보내지
# 못했습니다」로만 보이고 원인이 어디에도 안 남는다(2026-08-18 QA 에서 확인).
#
# **`gthread` 인 이유** — sync 워커는 한 요청이 워커 하나를 통째로 잡는다.
# 워커가 2개뿐이라 긴 문서 질문 둘이 겹치면 로그인·화면 로딩까지 전부 멈춘다.
# 스트리밍은 대부분 응답 대기(I/O)라 스레드가 맞고, DB 연결은 요청마다 새로
# 열리므로(`backend/db/connection.py` `database_connection()`) 스레드 안전하다.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", \
     "--workers", "2", "--worker-class", "gthread", "--threads", "8", \
     "--timeout", "600", "--access-logfile", "-"]
