# Web app image: builds the Angular app, then serves it with Caddy (which also proxies /api to Django).
# The Caddyfile is mounted from deploy/Caddyfile by docker compose.

FROM node:22-bookworm-slim AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npx ng build --configuration production

FROM caddy:2
COPY --from=build /src/dist/finance-tracker-ui/browser /srv/app
