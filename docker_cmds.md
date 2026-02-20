## Logs
### Front End
 docker compose -f docker-compose.production.yml logs frontend | tail -50
### Back End
 docker compose -f docker-compose.production.yml logs frontend | tail -50

## Rebuild

## Status
docker compose -f docker-compose.production.yml up -d
 docker compose -f docker-compose.production.yml logs frontend | tail -50
 docker compose -f docker-compose.production.yml build --no-cache frontend
 docker compose -f docker-compose.production.yml up -d frontend
 docker compose -f docker-compose.production.yml ps backend
 docker compose -f docker-compose.production.yml logs backend --tail 100
 docker compose -f docker-compose.production.yml build --no-cache backend
 docker compose -f docker-compose.production.yml up -d backend
 docker compose -f docker-compose.production.yml ps
 docker compose -f docker-compose.production.yml exec frontend tail -50 /var/log/nginx/error.log
 docker compose -f docker-compose.production.yml ps backend~
 docker compose -f docker-compose.production.yml ps backend
 docker compose -f docker-compose.production.yml ps backend
 docker compose -f docker-compose.production.yml logs backend --tail 200
 docker compose -f docker-compose.production.yml restart backend
 docker compose -f docker-compose.production.yml logs backend --tail 200
 docker compose -f docker-compose.production.yml build --no-cache backend
 docker compose -f docker-compose.production.yml up -d backend
 docker compose -f docker-compose.production.yml logs backend --tail 200
 docker compose -f docker-compose.production.yml restart backend
 docker compose -f docker-compose.production.yml build  backend
 docker compose -f docker-compose.production.yml restart backend
 docker ps
 export COMPOSE_FILE=/home/deploy/docker-compose.production.yml ; ./backup.sh 
 vi docker-compose.production.yml 
 vi docker-compose.local.yml 
 vi docker-compose.production.yml 
 vi docker-compose.production.yml 
 vi docker-compose.production.yml 
 vi docker-compose.production.yml 
 vi docker-compose.yml
 docker ps
 docker compose -f docker-compose.production.yml exec backend python manage.py migrate
 docker compose -f docker-compose.production.yml exec backend python manage.py makemigrations
 docker compose -f docker-compose.production.yml exec backend python manage.py migrate
 docker compose -f docker-compose.production.yml exec backend python manage.py makemigrations
 docker compose -f docker-compose.production.yml logs backend --tail 100
 docker compose -f docker-compose.production.yml exec backend python manage.py migrate food 0007 --fake
 docker compose -f docker-compose.production.yml exec backend python manage.py migrate food
 docker compose -f docker-compose.production.yml exec backend python manage.py migrate food\
 docker compose -f docker-compose.production.yml exec backend python manage.py migrate food
 docker ps
 docker compose -f docker-compose.production.yml exec backend python manage.py migrate food
 docker compose -f docker-compose.production.yml restart backend
 docker compose -f docker-compose.production.yml exec backend python manage.py migrate food
 docker ps
 docker compose -f docker-compose.production.yml logs backend --tail 100
 docker compose -f docker-compose.production.yml restart backend
 docker compose -f docker-compose.production.yml restart backend
 docker ps
 docker compose -f docker-compose.production.yml down backend
 docker compose -f docker-compose.production.yml build backend
 docker compose -f docker-compose.production.yml up backend
 docker compose -f docker-compose.production.yml build backend
 docker compose -f docker-compose.production.yml up backend


