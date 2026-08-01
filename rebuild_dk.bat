docker rm -f devenkalra-local-app
docker compose -f docker-compose.local.yml build --no-cache devenkalra-app
docker compose -f docker-compose.local.yml up -d devenkalra-app