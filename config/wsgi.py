import os

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
