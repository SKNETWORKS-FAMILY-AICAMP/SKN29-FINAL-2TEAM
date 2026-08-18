from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="unsafe-development-only-key")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
DATABASES = {}
RAW_DATABASE_URL = env(
    "DATABASE_URL",
    default="postgres://project_copilot:project_copilot@127.0.0.1:5432/project_copilot",
)
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "UNAUTHENTICATED_USER": None,
}

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:5173"])

# 메일은 비밀번호 재설정 링크에만 쓴다. 기본값이 console 백엔드라서 EMAIL_*을
# 설정하지 않은 팀원도 그대로 실행할 수 있고, 메일 본문은 터미널에 출력된다.
# 실제 발송이 필요할 때만 .env에서 EMAIL_HOST 이하를 채운다(Gmail은 계정
# 비밀번호가 아니라 앱 비밀번호가 필요하다).
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="halil <noreply@localhost>")

# 재설정 링크가 가리킬 프론트엔드 주소.
FRONTEND_BASE_URL = env("FRONTEND_BASE_URL", default="http://localhost:5173")

# Google Drive OAuth 웹 애플리케이션 자격증명. 실제 값은 로컬 `.env`에만 둔다.
GOOGLE_DRIVE_CLIENT_ID = env("GOOGLE_DRIVE_CLIENT_ID", default="")
GOOGLE_DRIVE_CLIENT_SECRET = env("GOOGLE_DRIVE_CLIENT_SECRET", default="")
GOOGLE_DRIVE_REDIRECT_URI = env(
    "GOOGLE_DRIVE_REDIRECT_URI",
    default="http://localhost:8000/api/connectors/google-drive/callback/",
)
JIRA_CLIENT_ID = env("JIRA_CLIENT_ID", default="")
JIRA_CLIENT_SECRET = env("JIRA_CLIENT_SECRET", default="")
JIRA_REDIRECT_URI = env(
    "JIRA_REDIRECT_URI",
    default="http://localhost:8000/api/connectors/jira/callback/",
)

# 파일 저장소 선택 값. `local` 과 `s3` 둘이다(2026-08-18 배선).
#
# **읽는 곳은 여기가 아니라 `backend/services/storage.py` 다.** 그 모듈은 Django
# 밖(스크립트·워커)에서도 import 되므로 settings 대신 환경 변수를 직접 본다.
# 이 줄은 값의 존재와 기본값을 한곳에 적어 두는 용도다.
OBJECT_STORAGE_PROVIDER = env("OBJECT_STORAGE_PROVIDER", default="local")

# 배포된 런타임 코드 버전(git commit SHA). agent_run.runtime_profile_version에
# 그대로 실려 나간다(services/agent_runtime/tracing) — 장애·평가 재현 시 "그때
# 배포된 코드가 정확히 무엇이었는가"를 알려면 필요하다. 배포 파이프라인이
# `docker build --build-arg GIT_COMMIT_SHA=$(git rev-parse HEAD)`로 안 채우면
# (Dockerfile 참고) 로컬 등에서는 계속 빈 값이다 — 가짜 값을 만들지 않고 None으로
# 둔다(2026-08-14).
RUNTIME_PROFILE_VERSION = env("RUNTIME_PROFILE_VERSION", default="") or None

# No operational default is provided for secrets or external addresses. The
# integration validates these settings at the boundary where they are needed.
RUNPOD_API_KEY = env("RUNPOD_API_KEY", default="")
RUNPOD_ENDPOINT_ID = env("RUNPOD_ENDPOINT_ID", default="")
PUBLIC_BACKEND_BASE_URL = env("PUBLIC_BACKEND_BASE_URL", default="")
RUNPOD_JOB_TTL_MS = env.int("RUNPOD_JOB_TTL_MS", default=3_600_000)
RUNPOD_EXECUTION_TIMEOUT_MS = env.int(
    "RUNPOD_EXECUTION_TIMEOUT_MS", default=1_800_000
)
DOCUMENT_DOWNLOAD_TOKEN_MAX_AGE_SECONDS = env.int(
    "DOCUMENT_DOWNLOAD_TOKEN_MAX_AGE_SECONDS", default=900
)
# 질의 임베딩이 워커를 기다리는 한도. 대부분 콜드 스타트를 기다리는 시간이라
# 이미지 pull + 모델 다운로드가 끝날 만큼은 줘야 한다.
RUNPOD_EMBED_WAIT_SECONDS = env.int("RUNPOD_EMBED_WAIT_SECONDS", default=600)

# 웹 검색(Tavily). **없으면 그 도구만 안 도는 것이 정상이다** — 키가 없다고
# 에이전트 전체가 죽으면 안 되고, "웹을 못 봤다"는 사실이 답에 드러나야 한다.
#
# Tavily 를 고른 이유: LLM 에이전트용이라 링크 목록이 아니라 **본문 조각**을
# 준다. 링크만 오면 우리가 다시 크롤링해야 하고, 그건 SSRF·robots·인코딩까지
# 딸려오는 별개의 일이다.
WEB_SEARCH_API_KEY = env("WEB_SEARCH_API_KEY", default="")
WEB_SEARCH_TIMEOUT_SECONDS = env.int("WEB_SEARCH_TIMEOUT_SECONDS", default=20)

OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
# 검색어 생성 전용 모델. 최종 정리와 따로 두는 이유는 services/task_extraction
# 쪽 주석에 실측과 함께 적어 뒀다 — 같은 일에 Sol 은 Luna 의 수백 배가 든다.
#: **모델은 여기서 고정하지 않는다 (2026-08-12).**
#:
#: 예전에는 `OPENAI_MODEL`·`OPENAI_PLAN_MODEL`·`OPENAI_REASONING_EFFORT` 가
#: `.env` 에 박혀 있어서, 화면에서 모델을 골라도 실제로는 그 값으로 돌았다.
#: 이제 모델은 **에이전트가 들고 있고**(설정 > Model, 에이전트 빌더), 코드
#: 기본값은 각 모듈의 상수다. `.env` 에는 **키만** 둔다.
#: Claude 계열을 부를 때 쓴다. OpenAI 호환 경로라 별도 SDK 는 없다.
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")
# OpenAI 처리 대기열. priority 는 지연이 짧은 대신 비싸다. 계정이 안 열어 준
# 티어를 주면 요청이 거절되므로 기본은 auto 로 둔다.
OPENAI_SERVICE_TIER = env("OPENAI_SERVICE_TIER", default="auto")
CHUNKING_MAX_TOKENS = env.int("CHUNKING_MAX_TOKENS", default=512)
CHUNKING_MERGE_PEERS = env.bool("CHUNKING_MERGE_PEERS", default=True)
