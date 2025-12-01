# Build stage for Go binary
FROM golang:1.25-alpine AS builder

# Install build dependencies
RUN apk add --no-cache gcc musl-dev sqlite-dev

WORKDIR /app

# Copy go mod files first for better caching
COPY go.mod go.sum ./
RUN go mod download

# Copy source code
COPY cmd/ ./cmd/
COPY internal/ ./internal/

# Build with CGO for sqlite3
ENV CGO_ENABLED=1
RUN go build -o homesightd ./cmd/homesightd

# Final image
FROM alpine:latest

# Install runtime dependencies
RUN apk add --no-cache ca-certificates sqlite-libs tzdata

WORKDIR /app

# Copy binary from builder
COPY --from=builder /app/homesightd .

# Copy pre-built web UI (built on host with npm run build)
COPY web-ui/dist/ ./web-ui/dist/

# Create data directory for SQLite
RUN mkdir -p /var/lib/homesight

# Config is mounted at runtime
# Database is mounted at runtime

EXPOSE 8080

# Environment defaults (can be overridden)
ENV HOMESIGHT_CONFIG=/app/config.yaml

ENTRYPOINT ["./homesightd"]