# syntax=docker/dockerfile:1
# 构建阶段：锁文件确保前端依赖可复现。
# Debian-based Node avoids the Alpine/npm install issue observed in Docker Desktop builds.
FROM node:20-slim AS build
WORKDIR /app

COPY package.json package-lock.json ./
# `npm ci` keeps Docker builds reproducible; devDependencies are required by the Vite build.
RUN npm ci --include=dev --no-audit --no-fund \
    && test -x node_modules/.bin/tsc
COPY . .
RUN npm run build

# 运行阶段：只保留静态产物与 Nginx 同源反向代理。
FROM nginx:1.27-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
