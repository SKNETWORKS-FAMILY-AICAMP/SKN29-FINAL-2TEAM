# 스테이지가 둘이다. **마지막 스테이지가 기본값**이므로 `dev` 를 맨 뒤에 둔다 —
# 로컬 `docker-compose.yml` 은 target 을 안 적고도 지금까지처럼 개발 서버를 받는다.
# AWS 는 `docker-compose.aws.yml` 이 `target: static` 으로 정적 빌드를 고른다.

FROM node:22-alpine AS deps

WORKDIR /app

COPY package*.json ./
RUN npm ci

# ── AWS: 정적 빌드 ────────────────────────────────────────────────────
FROM deps AS build

COPY . .

# ⚠ Vite 는 `VITE_*` 를 **빌드 시점에 번들로 구워 넣는다.** 컨테이너를 띄울 때
# 주는 환경변수는 정적 파일에 영향을 주지 않는다. 그래서 런타임이 아니라
# build arg 로 받는다. 주소가 바뀌면 이미지를 다시 빌드해야 한다.
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

FROM caddy:2-alpine AS static

# 앞단 Caddy 가 `reverse_proxy frontend:5173` 으로 부르므로 포트를 그대로 쓴다.
COPY Caddyfile.static /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv

EXPOSE 5173

# ── 로컬 개발: Vite 개발 서버(HMR) ────────────────────────────────────
# 맨 뒤에 둬야 target 을 안 적었을 때 이쪽이 걸린다.
FROM deps AS dev

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
