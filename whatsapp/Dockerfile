# Puente WhatsApp de EDI (Node 22 + Baileys). ~150 MB, sin navegador.
FROM node:22-slim
ENV NODE_ENV=production WA_AUTH_DIR=/auth PORT=3000
WORKDIR /srv
COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund && npm cache clean --force
COPY index.mjs ./
RUN mkdir -p /auth
EXPOSE 3000
CMD ["node", "index.mjs"]
