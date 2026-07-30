"""비밀번호 재설정 안내 메일.

메일은 이 용도로만 쓴다. `EMAIL_BACKEND` 기본값이 console이라 별도 설정
없이도 동작하며, 그때는 본문이 서버 터미널에 출력된다.
"""

from urllib.parse import quote

from django.conf import settings
from django.core.mail import send_mail

SUBJECT = "[halil] 비밀번호 재설정 안내"

BODY = """{display_name}님, 안녕하세요.

halil 계정의 비밀번호 재설정이 요청되었습니다.
아래 링크에서 새 비밀번호를 설정해 주세요.

{link}

이 링크는 1시간 동안만 유효하며, 비밀번호를 한 번 변경하면 즉시 만료됩니다.
본인이 요청한 것이 아니라면 이 메일을 무시하셔도 됩니다. 비밀번호는 그대로 유지됩니다.
"""


def send_password_reset_mail(*, to_email: str, display_name: str, token: str) -> None:
    link = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/reset-password?token={quote(token)}"
    send_mail(
        SUBJECT,
        BODY.format(display_name=display_name, link=link),
        settings.DEFAULT_FROM_EMAIL,
        [to_email],
        fail_silently=False,
    )
