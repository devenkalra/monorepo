FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

COPY devenkalra.com/frontend/package*.json ./
RUN npm ci

COPY devenkalra.com/frontend/ ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY devenkalra.com/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

COPY devenkalra.com/backend/ ./
COPY --from=frontend-builder /frontend/dist ./frontend_dist

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate && python manage.py ensure_music_library_page && python manage.py collectstatic --noinput && gunicorn backend.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 3600"]
