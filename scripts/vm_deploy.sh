#!/bin/bash
#
# One-Command VM Deployment Script for Precious Metals Trading System
# Usage: ./vm_deploy.sh <IP_ADDRESS> <PASSWORD>
#

set -e

# Configuration
VM_IP="${1:-165.227.191.236}"
VM_PASS="${2:-Cl@ud#123XaUX#G}"
VM_USER="root"
LOCAL_DIR="/home/user/claudemaker"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
echo_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
echo_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# SSH command helper
run_ssh() {
    sshpass -p "$VM_PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 ${VM_USER}@${VM_IP} "$1"
}

# SCP helper
run_scp() {
    sshpass -p "$VM_PASS" scp -o StrictHostKeyChecking=no -r "$1" ${VM_USER}@${VM_IP}:"$2"
}

echo_info "=== Precious Metals Trading System - VM Deployment ==="
echo_info "Target: ${VM_USER}@${VM_IP}"
echo ""

# Step 1: Test connection
echo_info "Step 1: Testing connection..."
if ! run_ssh "echo 'Connection OK'"; then
    echo_error "Cannot connect to VM. Please check:"
    echo "  - Is the VM running?"
    echo "  - Is the IP correct?"
    echo "  - Is SSH port 22 open?"
    exit 1
fi

# Step 2: Install dependencies
echo_info "Step 2: Installing dependencies..."
run_ssh "apt-get update && apt-get install -y python3 python3-pip redis-server postgresql postgresql-contrib"

# Step 3: Install Python packages
echo_info "Step 3: Installing Python packages..."
run_ssh "pip3 install psycopg2-binary redis requests psutil numpy schedule"

# Step 4: Create trader user if not exists
echo_info "Step 4: Setting up trader user..."
run_ssh "id trader 2>/dev/null || useradd -m -s /bin/bash trader"

# Step 5: Create directory structure
echo_info "Step 5: Creating directory structure..."
run_ssh "mkdir -p /home/trader/algo_trading/{services,config,models,logs/{data,signals,bots,learning},systemd,scripts}"
run_ssh "chown -R trader:trader /home/trader/algo_trading"

# Step 6: Deploy files
echo_info "Step 6: Deploying trading system files..."
run_scp "$LOCAL_DIR/services" "/home/trader/algo_trading/"
run_scp "$LOCAL_DIR/config" "/home/trader/algo_trading/"
run_scp "$LOCAL_DIR/systemd" "/home/trader/algo_trading/"
run_scp "$LOCAL_DIR/scripts" "/home/trader/algo_trading/"

# Step 7: Set permissions
echo_info "Step 7: Setting permissions..."
run_ssh "chown -R trader:trader /home/trader/algo_trading"
run_ssh "chmod +x /home/trader/algo_trading/scripts/*.sh"

# Step 8: Install systemd services
echo_info "Step 8: Installing systemd services..."
run_ssh "cp /home/trader/algo_trading/systemd/*.service /etc/systemd/system/"
run_ssh "systemctl daemon-reload"

# Step 9: Start Redis
echo_info "Step 9: Starting Redis..."
run_ssh "systemctl enable redis-server && systemctl start redis-server"

# Step 10: Initialize database schema
echo_info "Step 10: Initializing database..."
run_ssh "sudo -u postgres psql -c \"CREATE DATABASE trading_bot;\" 2>/dev/null || true"
run_ssh "sudo -u postgres psql -c \"CREATE USER trader WITH PASSWORD 'TradingBot2026Secure!';\" 2>/dev/null || true"
run_ssh "sudo -u postgres psql -c \"GRANT ALL PRIVILEGES ON DATABASE trading_bot TO trader;\""

# Step 11: Enable all services
echo_info "Step 11: Enabling services for auto-start..."
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

for service in "${SERVICES[@]}"; do
    run_ssh "systemctl enable $service" 2>/dev/null || true
done

# Step 12: Start all services
echo_info "Step 12: Starting all services..."
for service in "${SERVICES[@]}"; do
    echo_info "  Starting $service..."
    run_ssh "systemctl start $service" 2>/dev/null || echo_warn "  Failed to start $service"
    sleep 1
done

# Step 13: Verify
echo_info "Step 13: Verifying deployment..."
echo ""
echo "=== Service Status ==="
for service in "${SERVICES[@]}"; do
    status=$(run_ssh "systemctl is-active $service 2>/dev/null || echo 'inactive'")
    if [ "$status" == "active" ]; then
        echo -e "${GREEN}✓${NC} $service: $status"
    else
        echo -e "${RED}✗${NC} $service: $status"
    fi
done

echo ""
echo_info "=== Deployment Complete ==="
echo ""
echo "Your trading system is now running on the VM!"
echo ""
echo "Useful commands (SSH into VM first):"
echo "  ./scripts/status.sh        - Check all service status"
echo "  ./scripts/stop_all.sh      - Stop all services"
echo "  ./scripts/start_all.sh     - Start all services"
echo "  journalctl -u <service> -f - View live logs"
echo ""
echo "The system will automatically:"
echo "  - Collect 1-min data for Gold and Silver"
echo "  - Generate signals across all timeframes"
echo "  - Execute trades via 5 specialized bots"
echo "  - Learn and improve daily at 8 PM UTC"
echo ""
