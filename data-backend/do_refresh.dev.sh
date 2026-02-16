docker compose -f docker-compose.local.yml stop backend frontend-dev 
docker compose -f docker-compose.local.yml build backend frontend-dev 
docker compose -f docker-compose.local.yml up backend frontend-dev -d

