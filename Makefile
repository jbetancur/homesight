GOCMD=go
GOBUILD=$(GOCMD) build
GOCLEAN=$(GOCMD) clean
GOTEST=$(GOCMD) test
GOGET=$(GOCMD) get
BINARY_NAME=homesightd
BINARY_PATH=bin/$(BINARY_NAME)

.PHONY: all build clean test run install dev docker-build docker-rebuild docker-restart rebuild-all docker-fix-permissions

all: build

# Local Go build (for development without Docker)
build:
	$(GOBUILD) -o $(BINARY_PATH) ./cmd/homesightd

clean:
	$(GOCLEAN)
	rm -f $(BINARY_PATH)

test:
	$(GOTEST) -v ./...

run: build
	./$(BINARY_PATH)

install: build
	sudo ./scripts/install.sh

# Legacy dev script (deprecated - use 'make dev' instead)
dev-legacy:
	./scripts/dev.sh

deps:
	$(GOGET) -v ./...
	cd ai-sidecar && pip3 install -r requirements.txt

lint:
	golangci-lint run

fmt:
	gofmt -s -w .
	cd ai-sidecar && black .

# Docker permission fix
docker-fix-permissions:
	@echo "Fixing Docker permissions..."
	@./scripts/fix-docker-permissions.sh

# Build web UI
web-build:
	@echo "Building Web UI..."
	@cd web-ui && npm run build

# Docker commands - API
docker-build-api: web-build
	@echo "Building API Docker image..."
	@docker compose build api

docker-rebuild-api: web-build
	@echo "Rebuilding API Docker image (no cache)..."
	@docker compose build --no-cache api

# Docker commands - AI Sidecar
docker-build-ai:
	@echo "Building AI sidecar Docker image..."
	@docker compose build ai-sidecar

docker-rebuild-ai:
	@echo "Rebuilding AI sidecar with no cache..."
	@docker compose build --no-cache ai-sidecar

# Docker commands - All services
docker-build: web-build
	@echo "Building all Docker images..."
	@docker compose build api ai-sidecar

docker-rebuild: web-build
	@echo "Rebuilding all Docker images (no cache)..."
	@docker compose build --no-cache api ai-sidecar

docker-restart:
	@echo "Restarting all containers..."
	@docker compose restart

docker-restart-api:
	@echo "Restarting API container..."
	@docker compose restart api

docker-restart-ai:
	@echo "Restarting AI sidecar container..."
	@docker compose restart ai-sidecar

docker-logs:
	@echo "Showing all logs..."
	@docker compose logs -f

docker-logs-api:
	@echo "Showing API logs..."
	@docker compose logs -f api

docker-logs-ai:
	@echo "Showing AI sidecar logs..."
	@docker compose logs -f ai-sidecar

docker-stop:
	@echo "Stopping all containers..."
	@docker compose down

docker-up:
	@echo "Starting all containers..."
	@docker compose up -d

docker-ps:
	@docker compose ps

# Full rebuild commands
rebuild-all: web-build docker-rebuild
	@echo "✅ Full rebuild complete!"
	@echo ""
	@echo "Run './scripts/homesight.sh start' to start all services"

rebuild-api: docker-rebuild-api
	@echo "✅ API rebuilt!"
	@echo "Run 'docker compose restart api' or './scripts/homesight.sh restart'"

rebuild-ai: docker-rebuild-ai
	@echo "✅ AI sidecar rebuilt!"
	@echo "Run 'docker compose restart ai-sidecar'"

rebuild-quick: web-build docker-build docker-restart
	@echo "✅ Quick rebuild complete"

# Development shortcuts
start:
	@./scripts/homesight.sh start

stop:
	@./scripts/homesight.sh stop

restart:
	@./scripts/homesight.sh restart

status:
	@./scripts/homesight.sh status

# ==============================================================================
# Development Mode (Hot-reload for AI sidecar, quick rebuild for Go API)
# ==============================================================================

# Start all services in dev mode (AI sidecar with hot-reload)
dev:
	@echo "🔧 Starting HomeSight in development mode..."
	@docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
	@echo ""
	@echo "✅ Dev mode running!"
	@echo "   📝 Python changes: Auto-reload (no action needed)"
	@echo "   🔨 Go changes:     Run 'make rebuild-api && make dev-restart-api'"
	@echo "   📊 Status:         make status"
	@echo "   📜 Logs:           make dev-logs"

# Start only AI sidecar in dev mode
dev-ai:
	@echo "Starting AI sidecar in development mode (hot-reload enabled)..."
	@docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d ai-sidecar
	@echo "✅ AI sidecar running with hot-reload"
	@echo "   Edit files in ai-sidecar/ and changes apply automatically"
	@echo "   View logs: docker compose logs -f ai-sidecar"

# Stop dev mode
dev-stop:
	@echo "Stopping dev mode containers..."
	@docker compose -f docker-compose.yml -f docker-compose.dev.yml down

# View logs in dev mode
dev-logs:
	@docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f

# Restart a specific service in dev mode
dev-restart-api:
	@docker compose -f docker-compose.yml -f docker-compose.dev.yml restart api

dev-restart-ai:
	@docker compose -f docker-compose.yml -f docker-compose.dev.yml restart ai-sidecar
