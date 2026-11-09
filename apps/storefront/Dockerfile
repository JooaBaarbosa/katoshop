# Contexto de build: raiz do repositório.
FROM node:24.22.1-alpine AS build
ENV NEXT_TELEMETRY_DISABLED=1 COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable pnpm
WORKDIR /repo
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY packages packages
COPY apps/storefront apps/storefront
# defesa extra além do .dockerignore: o standalone copiaria qualquer .env carregado para a imagem
RUN found="$(find apps/storefront packages -name '.env*' ! -name '.env.example' -not -path '*/node_modules/*')"; \
    if [ -n "$found" ]; then echo "arquivo .env no contexto de build: $found" >&2; exit 1; fi
RUN pnpm install --frozen-lockfile --filter @katoshop/storefront...
RUN pnpm --filter @katoshop/storefront build

FROM node:24.22.1-alpine
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
WORKDIR /app
# saída standalone: server.js em apps/storefront, dependências rastreadas na raiz
COPY --from=build --chown=node:node /repo/apps/storefront/.next/standalone ./
COPY --from=build --chown=node:node /repo/apps/storefront/.next/static ./apps/storefront/.next/static
USER node
EXPOSE 3000
CMD ["node", "apps/storefront/server.js"]
