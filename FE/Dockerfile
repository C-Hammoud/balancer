# Web app image: builds the Angular app, then serves it with Caddy (which also proxies /api to Django).
# The Caddyfile is mounted from deploy/Caddyfile by docker compose.

FROM node:22-bookworm-slim AS build
WORKDIR /src
COPY package.json package-lock.json ./
# Retry dropped downloads (slow or flaky VPS network) and keep npm's download cache between
# builds, so a retry only fetches what is missing.
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund --prefer-offline \
      --fetch-retries=5 --fetch-retry-mintimeout=20000 --fetch-retry-maxtimeout=120000 \
      --fetch-timeout=600000
COPY . .
RUN npx ng build --configuration production

FROM caddy:2
COPY --from=build /src/dist/finance-tracker-ui/browser /srv/app
