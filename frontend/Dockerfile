# ── Stage 0: dev (hot reload via volume mount) ────────────────────────────────
# Source is NOT copied here — mount ./frontend:/app at runtime.
# node_modules are installed into the image and preserved via a named volume
# so the host directory doesn't shadow them.
#
# Usage (via docker-compose.dev.yml):
#   docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build frontend
FROM node:22-slim AS dev

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

EXPOSE 5173
CMD ["npm", "run", "dev"]

# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM node:22-slim AS build

WORKDIR /app

# Install deps before copying source so this layer is cached
COPY package.json package-lock.json ./
RUN npm ci

# Copy source and build
COPY . .
RUN npm run build

# ── Stage 2: serve ────────────────────────────────────────────────────────────
FROM nginx:alpine AS serve

# Replace default nginx config with ours
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from build stage
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
