# Build stage for React app
FROM node:25-alpine AS builder

WORKDIR /app

# Copy package files first for better caching
COPY web-ui/package.json web-ui/package-lock.json ./
RUN npm ci

# Copy source code
COPY web-ui/ ./

# Build production bundle
RUN npm run build

# Production stage with nginx
FROM nginx:alpine

# Copy built assets from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY docker/web-ui/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
