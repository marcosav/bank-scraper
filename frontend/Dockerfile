FROM node:22-alpine AS build

WORKDIR /app

RUN npm install -g pnpm

COPY ./app/package.json ./app/pnpm-lock.yaml ./

RUN pnpm install --frozen-lockfile

COPY ./app/ ./

RUN pnpm run build

FROM nginx:1.28-alpine

RUN rm -rf /usr/share/nginx/html/*

COPY --from=build /app/dist /usr/share/nginx/html

COPY ./generate-env-config.sh /docker-entrypoint.d/20-generate-env-config.sh
RUN chmod +x /docker-entrypoint.d/20-generate-env-config.sh

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]