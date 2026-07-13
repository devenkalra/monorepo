# Multi-stage: build people and cad frontends, serve with nginx
# Auth handled by Django (login at / and /login/)
# Build context must be monorepo root (parent of frontend/)
FROM node:20-alpine AS builder

WORKDIR /build

# Build people-frontend
COPY people-frontend/package*.json ./people-frontend/
RUN cd people-frontend && npm ci
COPY people-frontend/ ./people-frontend/
RUN cd people-frontend && npm run build

# Build cad-frontend
COPY cad-frontend/package*.json ./cad-frontend/
RUN cd cad-frontend && npm ci
COPY cad-frontend/ ./cad-frontend/
RUN cd cad-frontend && npm run build

# Build food-frontend
COPY food-frontend/package*.json ./food-frontend/
RUN cd food-frontend && npm ci
COPY food-frontend/ ./food-frontend/
RUN cd food-frontend && npm run build

# Build email-frontend
COPY email-frontend/package*.json ./email-frontend/
RUN cd email-frontend && npm ci
COPY email-frontend/ ./email-frontend/
RUN cd email-frontend && npm run build

# Combine outputs: people at /people-app/, cad at /cad-app/, food at /food-app/, email at /email-app/
# Root / and /login/ are proxied to Django for auth
RUN mkdir -p /out/people-app /out/cad-app /out/food-app /out/email-app && \
    cp people-frontend/dist/index.html /out/people-app/ && \
    cp -r people-frontend/dist/assets /out/people-app/ 2>/dev/null || true && \
    cp people-frontend/dist/favicon.svg /out/people-app/ 2>/dev/null || true && \
    cp cad-frontend/dist/index.html /out/cad-app/ && \
    cp -r cad-frontend/dist/assets /out/cad-app/ 2>/dev/null || true && \
    cp cad-frontend/dist/favicon.svg /out/cad-app/ 2>/dev/null || true && \
    cp food-frontend/dist/index.html /out/food-app/ && \
    cp -r food-frontend/dist/assets /out/food-app/ 2>/dev/null || true && \
    cp food-frontend/dist/favicon.svg /out/food-app/ 2>/dev/null || true && \
    cp email-frontend/dist/index.html /out/email-app/ && \
    cp -r email-frontend/dist/assets /out/email-app/ 2>/dev/null || true && \
    cp email-frontend/dist/favicon.svg /out/email-app/ 2>/dev/null || true

# Final nginx image
FROM nginx:alpine

ARG BUILD_ENV=production
COPY frontend/nginx.conf /etc/nginx/nginx.conf
COPY frontend/default.conf /etc/nginx/conf.d/default.conf
COPY frontend/default-local.conf /etc/nginx/conf.d/default-local.conf
COPY --from=builder /out /usr/share/nginx/html
# Use local config (HTTP only) when BUILD_ENV=local; otherwise exclude local config to avoid duplicate server blocks
RUN if [ "$BUILD_ENV" = "local" ]; then \
      mv /etc/nginx/conf.d/default.conf /etc/nginx/conf.d/default-prod.conf.bak && \
      mv /etc/nginx/conf.d/default-local.conf /etc/nginx/conf.d/default.conf; \
    else \
      rm -f /etc/nginx/conf.d/default-local.conf; \
    fi

RUN mkdir -p /etc/nginx/ssl && \
    adduser -D -H -u 1000 -s /sbin/nologin nginx 2>/dev/null || true && \
    chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx /var/log/nginx /etc/nginx/conf.d && \
    touch /var/run/nginx.pid && chown nginx:nginx /var/run/nginx.pid

EXPOSE 80 443
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost/health || exit 1
CMD ["nginx", "-g", "daemon off;"]
