from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False

# 개발 기본키로 production이 뜨는 것을 시작 단계에서 막는다. 짧거나 반복 문자인
# 키는 서명·비밀번호 재설정 토큰 등 Django 보안 기능 전체를 약하게 만든다.
if (
    SECRET_KEY.startswith("django-insecure-")  # noqa: F405
    or SECRET_KEY == "unsafe-development-only-key"  # noqa: F405
    or len(SECRET_KEY) < 50  # noqa: F405
    or len(set(SECRET_KEY)) < 5  # noqa: F405
):
    raise ImproperlyConfigured("production SECRET_KEY must be at least 50 characters and sufficiently random")

SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)  # noqa: F405
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False

# Caddy 가 TLS 를 끝내고 평문 HTTP 로 넘긴다. 이 줄이 없으면 Django 는 요청을
# 계속 http 로 보고, 위의 SECURE_SSL_REDIRECT 가 https 로 되돌리고, Caddy 가
# 다시 평문으로 넘기고 — **무한 리다이렉트**가 된다(ERR_TOO_MANY_REDIRECTS).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# https 로 들어오는 POST 는 Origin 이 여기 없으면 CSRF 검사에서 막힌다.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])  # noqa: F405
