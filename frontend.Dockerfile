FROM node:20-alpine AS build

WORKDIR /app

# Copy package files from root (monorepo-style setup)
COPY package*.json ./
COPY vite.config.js ./

# Install dependencies
RUN npm install

# Copy frontend source code
COPY frontend ./frontend

# Build frontend (Vite is configured with root: './frontend')
RUN npm run build

FROM nginx:alpine

# Copy built assets (Vite outputs to frontend/dist when root is set to ./frontend)
COPY --from=build /app/frontend/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

