import os
import threading

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

application = get_wsgi_application()

# 시각화 Tool의 Mermaid 엔진(QuickJS)은 첫 렌더가 ~5초다. 워커가 뜰 때 한 번
# 예열해 두면 실제 요청은 ~50ms로 끝난다. 서버 진입점에서만 부른다 —
# `manage.py test` 는 이 모듈을 import 하지 않는다.
try:
    from services.builtin_tools.visualization.renderer import _warm_in_background

    _warm_in_background()
except Exception:  # noqa: BLE001 - 예열 배선 실패가 서버 기동을 막으면 안 된다.
    pass


# 입력 가드레일(openai-guardrails)도 첫 import 가 수 초다(t3.micro 실측 openai 2.7s
# + guardrails 2.5s). 워커가 뜬 뒤 첫 채팅이 이걸 입력 검사 대기(12초) 안에서
# 치르다 시간을 넘겨, 「대화 차단」 팀의 첫 발화가 막혔다(2026-09-02, 2026-09-14
# 운영). 위 Mermaid 예열과 같은 이유로 여기서, 기동을 붙들지 않게 뒤에서 부른다.
def _warm_guardrails() -> None:
    try:
        import guardrails  # noqa: F401
        import openai  # noqa: F401
    except Exception:  # noqa: BLE001 - 설치 안 된 환경에서도 서버는 떠야 한다.
        pass


threading.Thread(target=_warm_guardrails, name="guardrails-warm", daemon=True).start()
