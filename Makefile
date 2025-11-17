GOCMD=go
GOBUILD=$(GOCMD) build
GOCLEAN=$(GOCMD) clean
GOTEST=$(GOCMD) test
GOGET=$(GOCMD) get
BINARY_NAME=homesightd
BINARY_PATH=bin/$(BINARY_NAME)

.PHONY: all build clean test run install dev

all: build

build:
	$(GOBUILD) -o $(BINARY_PATH) ./cmd/homesightd
	$(GOBUILD) -o bin/homesight-dashboard ./cmd/dashboard

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
