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
