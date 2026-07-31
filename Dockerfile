FROM python:3.13-slim

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
