#!/bin/bash
# HomeSight unified control script

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_DIR="$PROJECT_DIR/.pids"
LOG_DIR="$PROJECT_DIR/.logs"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

mkdir -p "$PID_DIR" "$LOG_DIR"

start_daemon() {
    echo -e "${GREEN}Starting HomeSight Daemon...${NC}"
    
    if [ -f "$PID_DIR/daemon.pid" ] && kill -0 $(cat "$PID_DIR/daemon.pid") 2>/dev/null; then
        echo -e "${YELLOW}Daemon already running (PID: $(cat "$PID_DIR/daemon.pid"))${NC}"
        return 0
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
        rm -f "$PID_DIR/daemon.pid"
        return 1
    fi
}

start_ai() {
    echo -e "${GREEN}Starting AI Sidecar...${NC}"
    
    if [ -f "$PID_DIR/ai.pid" ] && kill -0 $(cat "$PID_DIR/ai.pid") 2>/dev/null; then
        echo -e "${YELLOW}AI Sidecar already running (PID: $(cat "$PID_DIR/ai.pid"))${NC}"
        return 0
    fi
    
    if [ ! -d "$PROJECT_DIR/ai-sidecar/venv" ]; then
        echo -e "${YELLOW}Creating Python virtual environment...${NC}"
        cd "$PROJECT_DIR/ai-sidecar"
        python3 -m venv venv
        source venv/bin/activate
        pip install --upgrade pip -q
        pip install -r requirements.txt -q
        cd "$PROJECT_DIR"
    fi
    
    cd "$PROJECT_DIR/ai-sidecar"
    source venv/bin/activate
    nohup python main.py > "$LOG_DIR/ai.log" 2>&1 &
    echo $! > "$PID_DIR/ai.pid"
    cd "$PROJECT_DIR"
    sleep 2
    
    if kill -0 $(cat "$PID_DIR/ai.pid") 2>/dev/null; then
        echo -e "${GREEN}✅ AI Sidecar started (PID: $(cat "$PID_DIR/ai.pid"))${NC}"
        echo "   API: http://localhost:8001"
    else
        echo -e "${RED}❌ Failed to start AI sidecar${NC}"
        rm -f "$PID_DIR/ai.pid"
        return 1
    fi
}

start_docker() {
    echo -e "${GREEN}Starting Docker services...${NC}"
    
    cd "$PROJECT_DIR"
    sudo docker compose up -d 2>/dev/null
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Docker services started${NC}"
        echo "   MQTT: tcp://localhost:1883"
        echo "   Prometheus: http://localhost:9090"
    else
        echo -e "${YELLOW}⚠️  Docker services not started (optional)${NC}"
    fi
}

stop_daemon() {
    echo -e "${YELLOW}Stopping HomeSight Daemon...${NC}"
    
    if [ -f "$PID_DIR/daemon.pid" ]; then
        PID=$(cat "$PID_DIR/daemon.pid")
        if kill -0 $PID 2>/dev/null; then
            kill $PID
            sleep 1
            if kill -0 $PID 2>/dev/null; then
                kill -9 $PID 2>/dev/null
            fi
            echo -e "${GREEN}✅ Daemon stopped${NC}"
        else
            echo -e "${YELLOW}Daemon not running${NC}"
        fi
        rm -f "$PID_DIR/daemon.pid"
    else
        # Fallback: kill by name
        pkill -f "homesightd" 2>/dev/null && echo -e "${GREEN}✅ Daemon stopped${NC}"
    fi
}

stop_ai() {
    echo -e "${YELLOW}Stopping AI Sidecar...${NC}"
    
    if [ -f "$PID_DIR/ai.pid" ]; then
        PID=$(cat "$PID_DIR/ai.pid")
        if kill -0 $PID 2>/dev/null; then
            kill $PID
            sleep 1
            if kill -0 $PID 2>/dev/null; then
                kill -9 $PID 2>/dev/null
            fi
            echo -e "${GREEN}✅ AI Sidecar stopped${NC}"
        else
            echo -e "${YELLOW}AI Sidecar not running${NC}"
        fi
        rm -f "$PID_DIR/ai.pid"
    else
        # Fallback: kill by name
        pkill -f "ai-sidecar.*main.py" 2>/dev/null && echo -e "${GREEN}✅ AI Sidecar stopped${NC}"
    fi
}

stop_docker() {
    echo -e "${YELLOW}Stopping Docker services...${NC}"
    
    cd "$PROJECT_DIR"
    sudo docker compose down 2>/dev/null
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Docker services stopped${NC}"
    fi
}

show_status() {
    echo "🏠 HomeSight System Status"
    echo "=========================="
    echo ""
    
    # Daemon
    if [ -f "$PID_DIR/daemon.pid" ] && kill -0 $(cat "$PID_DIR/daemon.pid") 2>/dev/null; then
        echo -e "${GREEN}✅ Daemon: Running (PID: $(cat "$PID_DIR/daemon.pid"))${NC}"
        if curl -s http://localhost:8080/health > /dev/null 2>&1; then
            echo "   └─ API: http://localhost:8080 (healthy)"
        else
            echo "   └─ API: Not responding"
        fi
    else
        echo -e "${RED}❌ Daemon: Not running${NC}"
    fi
    
    # AI Sidecar
    if [ -f "$PID_DIR/ai.pid" ] && kill -0 $(cat "$PID_DIR/ai.pid") 2>/dev/null; then
        echo -e "${GREEN}✅ AI Sidecar: Running (PID: $(cat "$PID_DIR/ai.pid"))${NC}"
        if curl -s http://localhost:8001/health > /dev/null 2>&1; then
            echo "   └─ Service: http://localhost:8001 (healthy)"
        else
            echo "   └─ Service: Not responding"
        fi
    else
        echo -e "${RED}❌ AI Sidecar: Not running${NC}"
    fi
    
    # Docker
    echo ""
    echo "Docker Services:"
    if sudo docker ps --format "table {{.Names}}\t{{.Status}}" 2>/dev/null | grep -E "mosquitto|prometheus" > /dev/null; then
        sudo docker ps --format "  ✅ {{.Names}}: {{.Status}}" 2>/dev/null | grep -E "mosquitto|prometheus"
    else
        echo -e "  ${RED}❌ No Docker services running${NC}"
    fi
    
    echo ""
    echo "Logs:"
    echo "  Daemon: tail -f $LOG_DIR/daemon.log"
    echo "  AI:     tail -f $LOG_DIR/ai.log"
}

show_logs() {
    local service=$1
    case "$service" in
        daemon)
            tail -f "$LOG_DIR/daemon.log"
            ;;
        ai)
            tail -f "$LOG_DIR/ai.log"
            ;;
        *)
            echo "Available logs: daemon, ai"
            echo "Usage: $0 logs [daemon|ai]"
            ;;
    esac
}

case "${1:-}" in
    start)
        echo "🏠 Starting HomeSight..."
        echo ""
        start_daemon
        start_ai
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
    restart)
        echo "🏠 Restarting HomeSight..."
        echo ""
        stop_daemon
        stop_ai
        stop_docker
        sleep 1
        start_daemon
        start_ai
        start_docker
        echo ""
        show_status
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs "${2:-}"
        ;;
    dashboard)
        echo "🏠 Opening HomeSight Dashboard..."
        "$PROJECT_DIR/bin/homesight-dashboard"
        ;;
    start-daemon)
        start_daemon
        ;;
    start-ai)
        start_ai
        ;;
    start-docker)
        start_docker
        ;;
    stop-daemon)
        stop_daemon
        ;;
    stop-ai)
        stop_ai
        ;;
    stop-docker)
        stop_docker
        ;;
    *)
        echo "🏠 HomeSight Control Script"
        echo ""
        echo "Usage: $0 {start|stop|restart|status|logs|dashboard}"
        echo ""
        echo "Commands:"
        echo "  start          Start all services (daemon + AI + docker)"
        echo "  stop           Stop all services"
        echo "  restart        Restart all services"
        echo "  status         Show service status"
        echo "  logs [service] Show logs (daemon or ai)"
        echo "  dashboard      Open interactive TUI dashboard"
        echo ""
        echo "Individual controls:"
        echo "  start-daemon   Start only the daemon"
        echo "  start-ai       Start only the AI sidecar"
        echo "  start-docker   Start only Docker services"
        echo "  stop-daemon    Stop only the daemon"
        echo "  stop-ai        Stop only the AI sidecar"
        echo "  stop-docker    Stop only Docker services"
        echo ""
        echo "Examples:"
        echo "  $0 start           # Start everything"
        echo "  $0 stop            # Stop everything"
        echo "  $0 status          # Check status"
        echo "  $0 dashboard       # Open TUI dashboard"
        echo "  $0 logs daemon     # View daemon logs"
        exit 1
        ;;
esac
