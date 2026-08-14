from .base import *  # noqa: F403

DEBUG = False

SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)  # noqa: F405
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Caddy 가 TLS 를 끝내고 평문 HTTP 로 넘긴다. 이 줄이 없으면 Django 는 요청을
# 계속 http 로 보고, 위의 SECURE_SSL_REDIRECT 가 https 로 되돌리고, Caddy 가
# 다시 평문으로 넘기고 — **무한 리다이렉트**가 된다(ERR_TOO_MANY_REDIRECTS).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# https 로 들어오는 POST 는 Origin 이 여기 없으면 CSRF 검사에서 막힌다.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])  # noqa: F405
