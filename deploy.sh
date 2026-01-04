#!/bin/bash
#
# Gold Trading Bot - Deployment Script
# Deploys all automation components to the VPS
#

set -e

# Configuration
REMOTE_HOST="165.227.191.236"
REMOTE_USER="trader"
BOT_DIR="/home/trader"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Gold Trading Bot - Deployment Script  ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if running locally or remotely
if [ "$1" == "--local" ]; then
    echo -e "${YELLOW}Running local installation...${NC}"
    REMOTE=""
else
    echo -e "${YELLOW}Deploying to remote server: ${REMOTE_HOST}${NC}"
    REMOTE="ssh ${REMOTE_USER}@${REMOTE_HOST}"
fi

# Function to run command locally or remotely
run_cmd() {
    if [ -n "$REMOTE" ]; then
        $REMOTE "$1"
    else
        eval "$1"
    fi
}

# Function to copy files to remote
copy_files() {
    if [ -n "$REMOTE" ]; then
        echo -e "${YELLOW}Copying files to remote server...${NC}"
        scp -r "$SCRIPT_DIR"/*.py "${REMOTE_USER}@${REMOTE_HOST}:${BOT_DIR}/"
        scp "$SCRIPT_DIR"/systemd/*.service "${REMOTE_USER}@${REMOTE_HOST}:/tmp/"
    else
        echo -e "${YELLOW}Installing files locally...${NC}"
        cp "$SCRIPT_DIR"/*.py "$BOT_DIR/"
        cp "$SCRIPT_DIR"/systemd/*.service /tmp/
    fi
}

# Step 1: Install dependencies
echo -e "\n${GREEN}Step 1: Installing dependencies...${NC}"
run_cmd "pip3 install --quiet psutil requests schedule psycopg2-binary"

# Step 2: Copy automation scripts
echo -e "\n${GREEN}Step 2: Copying automation scripts...${NC}"
copy_files

# Step 3: Set permissions
echo -e "\n${GREEN}Step 3: Setting permissions...${NC}"
run_cmd "chmod +x ${BOT_DIR}/*.py"
run_cmd "chmod +x ${BOT_DIR}/*.sh 2>/dev/null || true"

# Step 4: Create directories
echo -e "\n${GREEN}Step 4: Creating directories...${NC}"
run_cmd "mkdir -p ${BOT_DIR}/backups"
run_cmd "mkdir -p ${BOT_DIR}/logs"

# Step 5: Install systemd services
echo -e "\n${GREEN}Step 5: Installing systemd services...${NC}"
run_cmd "sudo mv /tmp/*.service /etc/systemd/system/ 2>/dev/null || true"
run_cmd "sudo systemctl daemon-reload"

# Step 6: Enable and start services
echo -e "\n${GREEN}Step 6: Enabling services...${NC}"

# Stop existing processes first
run_cmd "pkill -f 'bot_supervisor.py' 2>/dev/null || true"
run_cmd "pkill -f 'telegram_commander.py' 2>/dev/null || true"
run_cmd "pkill -f 'report_generator.py' 2>/dev/null || true"

# Enable and start services
run_cmd "sudo systemctl enable trading-supervisor.service 2>/dev/null || true"
run_cmd "sudo systemctl enable telegram-commander.service 2>/dev/null || true"
run_cmd "sudo systemctl enable report-generator.service 2>/dev/null || true"
run_cmd "sudo systemctl enable trading-maintenance.timer 2>/dev/null || true"

run_cmd "sudo systemctl start trading-supervisor.service 2>/dev/null || true"
run_cmd "sudo systemctl start telegram-commander.service 2>/dev/null || true"
run_cmd "sudo systemctl start report-generator.service 2>/dev/null || true"
run_cmd "sudo systemctl start trading-maintenance.timer 2>/dev/null || true"

# Step 7: Create initial config if not exists
echo -e "\n${GREEN}Step 7: Creating initial configuration...${NC}"
run_cmd "python3 ${BOT_DIR}/bot_supervisor.py --init 2>/dev/null || true"

# Step 8: Verify deployment
echo -e "\n${GREEN}Step 8: Verifying deployment...${NC}"

# Check services
echo -e "\nService Status:"
run_cmd "systemctl is-active trading-supervisor.service 2>/dev/null || echo 'supervisor: not active'"
run_cmd "systemctl is-active telegram-commander.service 2>/dev/null || echo 'telegram: not active'"
run_cmd "systemctl is-active report-generator.service 2>/dev/null || echo 'reports: not active'"

# Check processes
echo -e "\nRunning Processes:"
run_cmd "ps aux | grep -E '(bot_supervisor|telegram_commander|report_generator)' | grep -v grep | wc -l"

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  Deployment Complete!                  ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Automation components installed:"
echo -e "  ${GREEN}✓${NC} Bot Supervisor (auto-restart, health monitoring)"
echo -e "  ${GREEN}✓${NC} Telegram Commander (remote control via Telegram)"
echo -e "  ${GREEN}✓${NC} Report Generator (daily/weekly reports)"
echo -e "  ${GREEN}✓${NC} Log Analyzer (trade insights)"
echo -e "  ${GREEN}✓${NC} Maintenance (log rotation, cleanup)"
echo ""
echo -e "Telegram Commands:"
echo -e "  /status  - Check bot status"
echo -e "  /balance - Account balances"
echo -e "  /pause   - Pause trading"
echo -e "  /resume  - Resume trading"
echo -e "  /help    - All commands"
echo ""
echo -e "Logs:"
echo -e "  ${BOT_DIR}/supervisor.log"
echo -e "  ${BOT_DIR}/telegram_commander.log"
echo -e "  ${BOT_DIR}/report_generator.log"
echo ""
