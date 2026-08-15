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

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-"]
