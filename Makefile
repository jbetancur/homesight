GOCMD=go
GOBUILD=$(GOCMD) build
GOCLEAN=$(GOCMD) clean
GOTEST=$(GOCMD) test
GOGET=$(GOCMD) get
BINARY_NAME=homesightd
BINARY_PATH=bin/$(BINARY_NAME)

.PHONY: all build clean test run install dev docker-build docker-rebuild docker-restart rebuild-all docker-fix-permissions

all: build

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

dev:
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

# Docker commands
docker-build:
	@echo "Building AI sidecar Docker image..."
	@docker-compose build ai-sidecar || (echo "" && echo "❌ Error: Permission denied." && echo "Run 'make docker-fix-permissions' to fix Docker permissions." && exit 1)

docker-rebuild:
	@echo "Rebuilding AI sidecar with no cache..."
	@docker-compose build --no-cache ai-sidecar

docker-restart:
	@echo "Restarting AI sidecar container..."
	@docker-compose restart ai-sidecar

docker-logs:
	@echo "Showing AI sidecar logs..."
	@docker-compose logs -f ai-sidecar

docker-stop:
	@echo "Stopping all containers..."
	@docker-compose down

docker-up:
	@echo "Starting all containers..."
	@docker-compose up -d

# Full rebuild commands
rebuild-all: clean build docker-rebuild
	@echo "✅ Full rebuild complete!"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Run 'make docker-up' to start containers"
	@echo "  2. Run './bin/homesightd' to start Go API"
	@echo "  3. Check logs with 'make docker-logs'"

rebuild-go: clean build
	@echo "✅ Go binaries rebuilt!"
	@echo "Run './bin/homesightd' to start the API"

rebuild-ai: docker-rebuild docker-up
	@echo "✅ AI sidecar rebuilt and restarted!"
	@echo "Check logs with 'make docker-logs'"

rebuild-quick: build docker-restart
	@echo "✅ Quick rebuild complete (Go + Docker restart)"
