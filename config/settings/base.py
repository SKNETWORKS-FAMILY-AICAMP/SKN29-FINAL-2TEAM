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

# 파일 저장소는 settings 값만 보고 선택한다. 애플리케이션 코드는 S3 SDK를 직접 호출하지 않는다.
OBJECT_STORAGE_PROVIDER = env("OBJECT_STORAGE_PROVIDER", default="local")
ANALYSIS_EXECUTION_MODE = env("ANALYSIS_EXECUTION_MODE", default="stub")
