#!/bin/bash
#
# Deployment script for Precious Metals Algo Trading System
# Deploys all microservices to the VM
#

set -e

# Configuration
REMOTE_USER="trader"
REMOTE_HOST="165.227.191.236"
REMOTE_DIR="/home/trader/algo_trading"
LOCAL_DIR="/home/user/claudemaker"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
echo_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
echo_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo_info "=== Precious Metals Algo Trading System Deployment ==="

# Check if running on VM or locally
if [ "$1" == "--local" ]; then
    echo_info "Local installation mode"
    INSTALL_DIR="/home/trader/algo_trading"
    mkdir -p $INSTALL_DIR
    cp -r $LOCAL_DIR/services $INSTALL_DIR/
    cp -r $LOCAL_DIR/config $INSTALL_DIR/
    cp -r $LOCAL_DIR/systemd $INSTALL_DIR/
    cp -r $LOCAL_DIR/scripts $INSTALL_DIR/
else
    echo_info "Remote deployment to $REMOTE_HOST"

    # Create remote directory structure
    ssh $REMOTE_USER@$REMOTE_HOST "mkdir -p $REMOTE_DIR/{services,config,models,logs/{data,signals,bots,learning},systemd,scripts}"

    # Sync files
    echo_info "Syncing files..."
    rsync -avz --progress \
        --exclude '__pycache__' \
        --exclude '*.pyc' \
        --exclude '.git' \
        --exclude '*.log' \
        $LOCAL_DIR/services/ $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/services/

    rsync -avz --progress \
        $LOCAL_DIR/config/ $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/config/

    rsync -avz --progress \
        $LOCAL_DIR/systemd/ $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/systemd/

    rsync -avz --progress \
        $LOCAL_DIR/scripts/ $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/scripts/

    INSTALL_DIR=$REMOTE_DIR
fi

echo_info "Installing Python dependencies..."
if [ "$1" == "--local" ]; then
    pip3 install --user psycopg2-binary redis requests psutil numpy schedule
else
    ssh $REMOTE_USER@$REMOTE_HOST "pip3 install --user psycopg2-binary redis requests psutil numpy schedule"
fi

echo_info "Installing Redis..."
if [ "$1" == "--local" ]; then
    if ! command -v redis-server &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y redis-server
        sudo systemctl enable redis-server
        sudo systemctl start redis-server
    fi
else
    ssh $REMOTE_USER@$REMOTE_HOST "sudo apt-get update && sudo apt-get install -y redis-server && sudo systemctl enable redis-server && sudo systemctl start redis-server" || echo_warn "Redis installation may have failed"
fi

echo_info "Setting up systemd services..."
SERVICES=(
    "data-collector"
    "timeframe-aggregator"
    "gold-signal-generator"
    "silver-signal-generator"
    "signal-aggregator"
    "bot-scalper"
    "bot-day-trader"
    "bot-swing"
    "bot-position"
    "bot-sniper"
    "trade-analyzer"
    "feedback-loop"
)

if [ "$1" == "--local" ]; then
    for service in "${SERVICES[@]}"; do
        sudo cp $LOCAL_DIR/systemd/${service}.service /etc/systemd/system/
    done
    sudo systemctl daemon-reload
else
    for service in "${SERVICES[@]}"; do
        ssh $REMOTE_USER@$REMOTE_HOST "sudo cp $REMOTE_DIR/systemd/${service}.service /etc/systemd/system/"
    done
    ssh $REMOTE_USER@$REMOTE_HOST "sudo systemctl daemon-reload"
fi

echo_info "Making scripts executable..."
if [ "$1" == "--local" ]; then
    chmod +x $INSTALL_DIR/scripts/*.sh
else
    ssh $REMOTE_USER@$REMOTE_HOST "chmod +x $REMOTE_DIR/scripts/*.sh"
fi

echo_info "Deployment complete!"
echo ""
echo "Next steps:"
echo "  1. Start services: ./scripts/start_all.sh"
echo "  2. Check status: ./scripts/status.sh"
echo "  3. View logs: journalctl -u <service-name> -f"
echo ""
echo "Services installed:"
for service in "${SERVICES[@]}"; do
    echo "  - $service"
done
