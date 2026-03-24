FROM node:20-alpine

WORKDIR /app

# Install dependencies (layer cache)
COPY frontend/package.json ./
RUN npm install

# Source is bind-mounted in dev — CMD starts dev server
ENV NODE_ENV=development

EXPOSE 5173

CMD ["npx", "vite", "--host", "0.0.0.0"]
