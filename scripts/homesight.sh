#!/bin/bash
# HomeSight unified control script

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_DIR="$PROJECT_DIR/.pids"
LOG_DIR="$PROJECT_DIR/logs"

# Dev mode flag
DEV_MODE=false
COMPOSE_CMD="docker compose"

# Parse --dev flag from any position
for arg in "$@"; do
    if [ "$arg" = "--dev" ]; then
        DEV_MODE=true
        COMPOSE_CMD="docker compose -f docker-compose.yml -f docker-compose.dev.yml"
    fi
done

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

mkdir -p "$PID_DIR" "$LOG_DIR"

check_binaries() {
    # No longer needed - using Docker containers
    return 0
}

start_mosquitto() {
    echo -e "${GREEN}Starting Mosquitto MQTT Broker (Docker)...${NC}"

    cd "$PROJECT_DIR"

    # Start with docker compose
    $COMPOSE_CMD up -d mosquitto

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Mosquitto started in Docker${NC}"
        echo "   MQTT: tcp://localhost:1883"
    else
        echo -e "${RED}❌ Failed to start Mosquitto${NC}"
        return 1
    fi
}

start_daemon() {
    echo -e "${GREEN}Starting HomeSight API (Docker)...${NC}"

    cd "$PROJECT_DIR"

    # Stop any existing container
    $COMPOSE_CMD stop api 2>/dev/null || true
    $COMPOSE_CMD rm -f api 2>/dev/null || true

    # Kill any host processes on port 8080
    if lsof -ti:8080 >/dev/null 2>&1; then
        echo -e "${YELLOW}Killing process on port 8080...${NC}"
        lsof -ti:8080 | xargs kill -9 2>/dev/null || true
        sleep 2
    fi

    # Build if image doesn't exist
    if ! docker images homesight-api --format "{{.Repository}}" | grep -q "homesight-api"; then
        echo -e "${YELLOW}Building API Docker image...${NC}"
        $COMPOSE_CMD build api
    fi

    # Start with docker compose
    $COMPOSE_CMD up -d api

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ HomeSight API started in Docker${NC}"
        echo "   API: http://localhost:8080"
    else
        echo -e "${RED}❌ Failed to start API${NC}"
        return 1
    fi
}

start_ai() {
    echo -e "${GREEN}Starting AI Sidecar (Docker)...${NC}"

    cd "$PROJECT_DIR"

    # Stop any existing container
    $COMPOSE_CMD stop ai-sidecar 2>/dev/null || true
    $COMPOSE_CMD rm -f ai-sidecar 2>/dev/null || true

    # Kill any host processes on port 8001
    if lsof -ti:8001 >/dev/null 2>&1; then
        echo -e "${YELLOW}Killing process on port 8001...${NC}"
        lsof -ti:8001 | xargs kill -9 2>/dev/null || true
        sleep 2
    fi

    # Start with docker compose
    $COMPOSE_CMD up -d ai-sidecar

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ AI Sidecar started in Docker${NC}"
        echo "   API: http://localhost:8001"
    else
        echo -e "${RED}❌ Failed to start AI sidecar${NC}"
        return 1
    fi
}

start_zwave() {
    echo -e "${GREEN}Starting ZWave (Docker)...${NC}"

    cd "$PROJECT_DIR"

    # Stop any existing container
    $COMPOSE_CMD stop zwavejs 2>/dev/null || true
    $COMPOSE_CMD rm -f zwavejs 2>/dev/null || true

    # Kill any host processes on port 8001
    if lsof -ti:8001 >/dev/null 2>&1; then
        echo -e "${YELLOW}Killing process on port 8001...${NC}"
        lsof -ti:8001 | xargs kill -9 2>/dev/null || true
        sleep 2
    fi

    # Start with docker compose
    $COMPOSE_CMD up -d zwavejs

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ ZWave started in Docker${NC}"
        echo "   API: http://localhost:8001"
    else
        echo -e "${RED}❌ Failed to start ZWave${NC}"
        return 1
    fi
}

start_web_ui() {
    echo -e "${GREEN}Starting Web UI (Docker)...${NC}"

    cd "$PROJECT_DIR"

    # Stop any existing container
    $COMPOSE_CMD stop web-ui 2>/dev/null || true
    $COMPOSE_CMD rm -f web-ui 2>/dev/null || true

    # Kill any host processes on port 5173
    if lsof -ti:5173 >/dev/null 2>&1; then
        echo -e "${YELLOW}Killing process on port 5173...${NC}"
        lsof -ti:5173 | xargs kill -9 2>/dev/null || true
        sleep 2
    fi

    # Build if image doesn't exist (check dev image in dev mode)
    local image_name="homesight-web-ui"
    if [ "$DEV_MODE" = true ]; then
        image_name="homesight-web-ui-dev"
    fi
    if ! docker images "$image_name" --format "{{.Repository}}" | grep -q "$image_name"; then
        echo -e "${YELLOW}Building Web UI Docker image...${NC}"
        $COMPOSE_CMD build web-ui
    fi

    # Start with docker compose
    $COMPOSE_CMD up -d web-ui

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Web UI started in Docker${NC}"
        echo "   URL: http://localhost:5173"
    else
        echo -e "${RED}❌ Failed to start Web UI${NC}"
        return 1
    fi
}

start_docker() {
    echo -e "${GREEN}Starting Docker services...${NC}"

    cd "$PROJECT_DIR"
    $COMPOSE_CMD up -d prometheus grafana 2>/dev/null

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Docker services started${NC}"
        echo "   Prometheus: http://localhost:9090"
        echo "   Grafana: http://localhost:3000 (admin/admin)"
    else
        echo -e "${YELLOW}⚠️  Docker services not started${NC}"
    fi
}

stop_daemon() {
    echo -e "${YELLOW}Stopping HomeSight API...${NC}"

    cd "$PROJECT_DIR"
    $COMPOSE_CMD stop api 2>/dev/null || true
    $COMPOSE_CMD rm -f api 2>/dev/null || true

    # Clean up any stray host processes
    pkill -9 -f "homesightd" 2>/dev/null || true
    lsof -ti:8080 2>/dev/null | xargs kill -9 2>/dev/null || true

    echo -e "${GREEN}✅ API stopped${NC}"
}

stop_mosquitto() {
    echo -e "${YELLOW}Stopping Mosquitto...${NC}"

    cd "$PROJECT_DIR"
    $COMPOSE_CMD stop mosquitto 2>/dev/null || true
    $COMPOSE_CMD rm -f mosquitto 2>/dev/null || true

    echo -e "${GREEN}✅ Mosquitto stopped${NC}"
}

stop_ai() {
    echo -e "${YELLOW}Stopping AI Sidecar...${NC}"

    cd "$PROJECT_DIR"
    $COMPOSE_CMD stop ai-sidecar 2>/dev/null || true
    $COMPOSE_CMD rm -f ai-sidecar 2>/dev/null || true

    pkill -9 -f "python.*main.py" 2>/dev/null || true
    pkill -9 -f "uvicorn" 2>/dev/null || true
    lsof -ti:8001 2>/dev/null | xargs kill -9 2>/dev/null || true

    echo -e "${GREEN}✅ AI Sidecar stopped${NC}"
}

stop_web_ui() {
    echo -e "${YELLOW}Stopping Web UI...${NC}"

    cd "$PROJECT_DIR"
    $COMPOSE_CMD stop web-ui 2>/dev/null || true
    $COMPOSE_CMD rm -f web-ui 2>/dev/null || true

    lsof -ti:5173 2>/dev/null | xargs kill -9 2>/dev/null || true

    echo -e "${GREEN}✅ Web UI stopped${NC}"
}

stop_docker() {
    echo -e "${YELLOW}Stopping Docker services...${NC}"

    cd "$PROJECT_DIR"
    $COMPOSE_CMD down 2>/dev/null || true

    echo -e "${GREEN}✅ Docker services stopped${NC}"
}

show_status() {
    echo "🏠 HomeSight System Status"
    echo "=========================="
    echo ""

    # Mosquitto
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^homesight-mosquitto$'; then
        echo -e "${GREEN}✅ Mosquitto: Running in Docker${NC}"
        echo "   └─ MQTT: tcp://localhost:1883"
    else
        echo -e "${RED}❌ Mosquitto: Not running${NC}"
    fi

    # API
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^homesight-api$'; then
        echo -e "${GREEN}✅ API: Running in Docker${NC}"
        if curl -s --max-time 2 http://localhost:8080/health > /dev/null 2>&1; then
            echo "   └─ API: http://localhost:8080 (healthy)"
        else
            echo "   └─ API: Not responding"
        fi
    else
        echo -e "${RED}❌ API: Not running${NC}"
    fi

    # AI Sidecar
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^homesight-ai-sidecar$'; then
        echo -e "${GREEN}✅ AI Sidecar: Running in Docker${NC}"
        if curl -s --max-time 5 http://localhost:8001/health > /dev/null 2>&1; then
            echo "   └─ API: http://localhost:8001 (healthy)"
        else
            echo "   └─ API: Not responding"
        fi
    else
        echo -e "${RED}❌ AI Sidecar: Not running${NC}"
    fi

    # ZWaveJS
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^homesight-zwavejs$'; then
        echo -e "${GREEN}✅ ZWaveJS: Running in Docker${NC}"
        echo "   └─ WebSocket: ws://localhost:3001"
        echo "   └─ UI: http://localhost:8091"
    else
        echo -e "${RED}❌ ZWaveJS: Not running${NC}"
    fi

    # Web UI
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^homesight-web-ui$'; then
        echo -e "${GREEN}✅ Web UI: Running in Docker${NC}"
        if curl -s --max-time 2 http://localhost:5173 > /dev/null 2>&1; then
            echo "   └─ URL: http://localhost:5173 (healthy)"
        else
            echo "   └─ URL: Not responding"
        fi
    else
        echo -e "${RED}❌ Web UI: Not running${NC}"
    fi

    # Docker monitoring services
    echo ""
    echo "Monitoring Services:"
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^homesight-prometheus$'; then
        echo -e "  ${GREEN}✅ Prometheus: http://localhost:9090${NC}"
    else
        echo -e "  ${RED}❌ Prometheus: Not running${NC}"
    fi
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^homesight-grafana$'; then
        echo -e "  ${GREEN}✅ Grafana: http://localhost:3001 (admin/admin)${NC}"
    else
        echo -e "  ${RED}❌ Grafana: Not running${NC}"
    fi

    echo ""
    echo "Logs:"
    echo "  Web UI:     docker compose logs -f web-ui"
    echo "  API:        docker compose logs -f api"
    echo "  AI:         docker compose logs -f ai-sidecar"
    echo "  MQTT:       docker compose logs -f mosquitto"
    echo "  ZWaveJS:    docker compose logs -f zwavejs"
}

clean_all() {
    echo -e "${RED}🧹 Cleaning all HomeSight processes...${NC}"

    stop_web_ui
    stop_daemon
    stop_ai
    stop_mosquitto
    stop_docker

    # Clean up PIDs
    rm -f "$PID_DIR"/*.pid 2>/dev/null || true

    # Clean up ports
    for port in 5173 8080 8001 1883 9090; do
        lsof -ti:$port 2>/dev/null | xargs kill -9 2>/dev/null || true
    done

    echo -e "${GREEN}✅ Clean complete${NC}"
}

case "${1:-}" in
    start)
        if [ "$DEV_MODE" = true ]; then
            echo "🏠 Starting HomeSight (DEV MODE)..."
        else
            echo "🏠 Starting HomeSight..."
        fi
        echo ""

        start_mosquitto
        start_daemon
        start_ai
        start_zwave
        start_web_ui
        start_docker

        echo ""
        show_status
        ;;
    stop)
        echo "🏠 Stopping HomeSight..."
        echo ""
        stop_web_ui
        stop_daemon
        stop_ai
        stop_mosquitto
        stop_docker
        ;;
    clean)
        clean_all
        ;;
    restart)
        if [ "$DEV_MODE" = true ]; then
            echo "🏠 Restarting HomeSight (DEV MODE)..."
        else
            echo "🏠 Restarting HomeSight..."
        fi
        echo ""

        stop_web_ui
        stop_daemon
        stop_ai
        stop_mosquitto
        stop_docker
        sleep 3
        start_mosquitto
        start_daemon
        start_ai
        start_zwave
        start_web_ui
        start_docker

        # Wait for services to be fully ready (AI sidecar loads LLM model)
        echo "Waiting for services to be ready..."
        sleep 15

        echo ""
        show_status
        ;;
    status)
        show_status
        ;;
    logs)
        case "${2:-}" in
            ui|web-ui) $COMPOSE_CMD logs -f web-ui ;;
            api|daemon) $COMPOSE_CMD logs -f api ;;
            ai) $COMPOSE_CMD logs -f ai-sidecar ;;
            mqtt|mosquitto) $COMPOSE_CMD logs -f mosquitto ;;
            zwave|zwavejs) $COMPOSE_CMD logs -f zwavejs ;;
            *) echo "Usage: $0 logs [ui|api|ai|mqtt|zwave]" ;;
        esac
        ;;
    build)
        echo "🏠 Building HomeSight Docker images..."
        echo ""

        # Build Docker images
        echo -e "${GREEN}Building Docker images...${NC}"
        cd "$PROJECT_DIR"
        $COMPOSE_CMD build api ai-sidecar web-ui

        echo -e "${GREEN}✅ Build complete${NC}"
        ;;
    rebuild)
        echo "🏠 Rebuilding HomeSight (no cache)..."
        echo ""

        # Rebuild Docker images without cache
        echo -e "${GREEN}Rebuilding Docker images (no cache)...${NC}"
        cd "$PROJECT_DIR"
        $COMPOSE_CMD build --no-cache api ai-sidecar web-ui

        echo -e "${GREEN}✅ Rebuild complete${NC}"
        ;;
    *)
        echo "🏠 HomeSight Control Script"
        echo ""
        echo "Usage: $0 {start|stop|restart|clean|status|logs|build|rebuild} [--dev]"
        echo ""
        echo "Commands:"
        echo "  start    Start all services"
        echo "  stop     Stop all services"
        echo "  restart  Restart all services"
        echo "  clean    Kill all processes and clean ports"
        echo "  status   Show service status"
        echo "  logs     Show logs (ui|api|ai|mqtt|zwave)"
        echo "  build    Build Docker images"
        echo "  rebuild  Rebuild Docker images (no cache)"
        echo ""
        echo "Options:"
        echo "  --dev    Use docker-compose.dev.yml for hot-reloading"
        exit 1
        ;;
esac
