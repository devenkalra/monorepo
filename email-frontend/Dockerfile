# Standalone Dockerfile for email-frontend development
FROM node:20-alpine

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci

# Copy source code
COPY . .

EXPOSE 5176

CMD ["npm", "run", "dev"]
