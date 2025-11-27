#!/bin/bash
# HomeSight unified control script

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_DIR="$PROJECT_DIR/.pids"
LOG_DIR="$PROJECT_DIR/logs"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

mkdir -p "$PID_DIR" "$LOG_DIR"

check_binaries() {
    local missing=0

    if [ ! -f "$PROJECT_DIR/bin/homesightd" ]; then
        echo -e "${RED}❌ Missing: bin/homesightd${NC}"
        missing=1
    fi

    return $missing
}

start_daemon() {
    echo -e "${GREEN}Starting HomeSight Daemon...${NC}"

    if [ -f "$PID_DIR/daemon.pid" ] && kill -0 $(cat "$PID_DIR/daemon.pid") 2>/dev/null; then
        echo -e "${YELLOW}Daemon already running (PID: $(cat "$PID_DIR/daemon.pid"))${NC}"
        return 0
    fi

    # Check if binary exists
    if [ ! -f "$PROJECT_DIR/bin/homesightd" ]; then
        echo -e "${RED}❌ Daemon binary not found: $PROJECT_DIR/bin/homesightd${NC}"
        echo ""
        echo "The binary may not be installed. Please check that:"
        echo "  - The daemon binary has been installed to bin/homesightd"
        echo "  - Installation package was properly deployed"
        echo ""
        return 1
    fi

    cd "$PROJECT_DIR"
    export HOMESIGHT_CONFIG="$PROJECT_DIR/config.yaml"
    mkdir -p data

    nohup ./bin/homesightd > "$LOG_DIR/daemon.log" 2>&1 &
    echo $! > "$PID_DIR/daemon.pid"
    sleep 2

    if kill -0 $(cat "$PID_DIR/daemon.pid") 2>/dev/null; then
        echo -e "${GREEN}✅ Daemon started (PID: $(cat "$PID_DIR/daemon.pid"))${NC}"
        echo "   API: http://localhost:8080"
    else
        echo -e "${RED}❌ Failed to start daemon${NC}"
        cat "$LOG_DIR/daemon.log"
        rm -f "$PID_DIR/daemon.pid"
        return 1
    fi
}

start_ai() {
    echo -e "${GREEN}Starting AI Sidecar (Docker)...${NC}"

    cd "$PROJECT_DIR"

    # Stop any existing container
    docker compose stop ai-sidecar 2>/dev/null || true
    docker compose rm -f ai-sidecar 2>/dev/null || true

    # Kill any host processes on port 8001
    if lsof -ti:8001 >/dev/null 2>&1; then
        echo -e "${YELLOW}Killing process on port 8001...${NC}"
        lsof -ti:8001 | xargs kill -9 2>/dev/null || true
        sleep 2
    fi

    # Start with docker compose
    docker compose up -d ai-sidecar

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
    docker compose stop zwavejs 2>/dev/null || true
    docker compose rm -f zwavejs 2>/dev/null || true

    # Kill any host processes on port 8001
    if lsof -ti:8001 >/dev/null 2>&1; then
        echo -e "${YELLOW}Killing process on port 8001...${NC}"
        lsof -ti:8001 | xargs kill -9 2>/dev/null || true
        sleep 2
    fi

    # Start with docker compose
    docker compose up -d zwavejs

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ ZWave started in Docker${NC}"
        echo "   API: http://localhost:8001"
    else
        echo -e "${RED}❌ Failed to start ZWave${NC}"
        return 1
    fi
}

start_docker() {
    echo -e "${GREEN}Starting Docker services...${NC}"

    cd "$PROJECT_DIR"
    docker compose up -d prometheus grafana 2>/dev/null

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Docker services started${NC}"
        echo "   Prometheus: http://localhost:9090"
        echo "   Grafana: http://localhost:3000 (admin/admin)"
    else
        echo -e "${YELLOW}⚠️  Docker services not started${NC}"
    fi
}

stop_daemon() {
    echo -e "${YELLOW}Stopping HomeSight Daemon...${NC}"

    if [ -f "$PID_DIR/daemon.pid" ]; then
        PID=$(cat "$PID_DIR/daemon.pid")
        kill $PID 2>/dev/null || true
        sleep 1
        kill -9 $PID 2>/dev/null || true
        rm -f "$PID_DIR/daemon.pid"
    fi

    pkill -9 -f "homesightd" 2>/dev/null || true
    lsof -ti:8080 2>/dev/null | xargs kill -9 2>/dev/null || true

    echo -e "${GREEN}✅ Daemon stopped${NC}"
}

stop_ai() {
    echo -e "${YELLOW}Stopping AI Sidecar...${NC}"

    cd "$PROJECT_DIR"
    docker compose stop ai-sidecar 2>/dev/null || true
    docker compose rm -f ai-sidecar 2>/dev/null || true

    pkill -9 -f "python.*main.py" 2>/dev/null || true
    pkill -9 -f "uvicorn" 2>/dev/null || true
    lsof -ti:8001 2>/dev/null | xargs kill -9 2>/dev/null || true

    echo -e "${GREEN}✅ AI Sidecar stopped${NC}"
}

stop_docker() {
    echo -e "${YELLOW}Stopping Docker services...${NC}"

    cd "$PROJECT_DIR"
    docker compose down 2>/dev/null || true

    echo -e "${GREEN}✅ Docker services stopped${NC}"
}

show_status() {
    echo "🏠 HomeSight System Status"
    echo "=========================="
    echo ""

    # Daemon
    if [ -f "$PID_DIR/daemon.pid" ] && kill -0 $(cat "$PID_DIR/daemon.pid") 2>/dev/null; then
        echo -e "${GREEN}✅ Daemon: Running (PID: $(cat "$PID_DIR/daemon.pid"))${NC}"
        if curl -s --max-time 2 http://localhost:8080/health > /dev/null 2>&1; then
            echo "   └─ API: http://localhost:8080 (healthy)"
        else
            echo "   └─ API: Not responding"
        fi
    else
        echo -e "${RED}❌ Daemon: Not running${NC}"
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

    # Docker
    echo ""
    echo "Docker Services:"
    if docker ps --format "table {{.Names}}\t{{.Status}}" 2>/dev/null | grep -E "prometheus" > /dev/null; then
        docker ps --format "  ✅ {{.Names}}: {{.Status}}" 2>/dev/null | grep -E "prometheus"
    else
        echo -e "  ${RED}❌ No Docker services running${NC}"
    fi

    echo ""
    echo "Logs:"
    echo "  Daemon: tail -f $LOG_DIR/daemon.log"
    echo "  AI:     docker-compose logs -f ai-sidecar"
}

clean_all() {
    echo -e "${RED}🧹 Cleaning all HomeSight processes...${NC}"

    stop_daemon
    stop_ai
    stop_docker

    # Clean up PIDs
    rm -f "$PID_DIR"/*.pid 2>/dev/null || true

    # Clean up ports
    for port in 8080 8001 9090; do
        lsof -ti:$port 2>/dev/null | xargs kill -9 2>/dev/null || true
    done

    echo -e "${GREEN}✅ Clean complete${NC}"
}

case "${1:-}" in
    start)
        echo "🏠 Starting HomeSight..."
        echo ""

        # Check binaries first
        if ! check_binaries; then
            echo ""
            echo "❌ Missing required binaries. Please ensure binaries are installed."
            echo ""
            exit 1
        fi

        start_daemon
        start_ai
        start_zwave
        start_docker

        echo ""
        show_status
        ;;
    stop)
        echo "🏠 Stopping HomeSight..."
        echo ""
        stop_daemon
        stop_ai
        stop_docker
        ;;
    clean)
        clean_all
        ;;
    restart)
        echo "🏠 Restarting HomeSight..."
        echo ""

        # Check binaries first
        if ! check_binaries; then
            echo ""
            echo "❌ Missing required binaries. Please ensure binaries are installed."
            echo ""
            exit 1
        fi

        stop_daemon
        stop_ai
        stop_docker
        sleep 3
        start_daemon
        start_ai
        start_zwave
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
            daemon) tail -f "$LOG_DIR/daemon.log" ;;
            ai) docker compose logs -f ai-sidecar ;;
            *) echo "Usage: $0 logs [daemon|ai]" ;;
        esac
        ;;
    *)
        echo "🏠 HomeSight Control Script"
        echo ""
        echo "Usage: $0 {start|stop|restart|clean|status|logs}"
        echo ""
        echo "Commands:"
        echo "  start    Start all services"
        echo "  stop     Stop all services"
        echo "  restart  Restart all services"
        echo "  clean    Kill all processes and clean ports"
        echo "  status   Show service status"
        echo "  logs     Show logs (daemon or ai)"
        exit 1
        ;;
esac
