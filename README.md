# AI 프로젝트 운영 코파일럿

Django·Django REST Framework 기반 API와 React·Vite 프론트엔드 실행 환경을 포함한 PM 지원 플랫폼 베이스 코드다. React 화면 HTML/CSS는 Figma 담당 팀원이 별도로 구현한다.

## 현재 구현

- Django Admin 기반 People DB 관리 기반
- DRF 기반 프로젝트·조직·직원 조회와 분석 실행 생성·상태 조회 API
- React + Vite + TypeScript 실행 환경과 API Client
- PostgreSQL/pgvector Docker Compose 구성
- 로컬·AWS 전환을 위한 설정 경계

문서 파싱, PKM, Snapshot, Readiness, 업무량, 추천, 검증 엔진은 서비스 모듈 경계만 마련된 상태다.

## 로컬 실행

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements\local.txt
$env:USE_SQLITE = "True"
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo_people
python manage.py runserver
```

관리자 화면은 `http://127.0.0.1:8000/admin/`, 상태 확인 API는 `/api/health/`, React 개발 서버는 `http://127.0.0.1:5173/`로 접근한다. React 화면은 현재 의도적으로 비어 있다.

PostgreSQL 컨테이너를 사용할 때는 `.env`의 `USE_SQLITE=False`를 유지하고 다음을 실행한다.

```powershell
docker compose -f infra/docker/docker-compose.yml up --build
```

팀원별 Docker 설치·실행은 `docs/0_개발환경/로컬_Docker_개발환경_설치_매뉴얼.md`, 구현 상태와 다음 작업은 `docs/0_개발환경/초기_구성_상태.md`를 따른다.
