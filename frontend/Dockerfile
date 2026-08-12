# Standard Vite SPA build, served by nginx.
# Requires a package.json/package-lock.json at the frontend root (the source
# tree is currently a scaffold). Multi-stage keeps the runtime image tiny.
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
RUN addgroup -S aegis && adduser -S aegis -G aegis
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN chown -R aegis:aegis /usr/share/nginx/html /var/cache/nginx /var/log/nginx \
    && touch /var/run/nginx.pid && chown aegis:aegis /var/run/nginx.pid
USER aegis
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
