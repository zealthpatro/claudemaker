#!/bin/bash
#
# Stop all trading system services
#

set -e

RED='\033[0;31m'
NC='\033[0m'

echo -e "${RED}Stopping Precious Metals Trading System...${NC}"

# Stop in reverse order

# Learning Layer
sudo systemctl stop feedback-loop 2>/dev/null || true
sudo systemctl stop trade-analyzer 2>/dev/null || true

# Bot Layer
sudo systemctl stop bot-sniper 2>/dev/null || true
sudo systemctl stop bot-position 2>/dev/null || true
sudo systemctl stop bot-swing 2>/dev/null || true
sudo systemctl stop bot-day-trader 2>/dev/null || true
sudo systemctl stop bot-scalper 2>/dev/null || true

# Risk Manager
sudo systemctl stop risk-manager 2>/dev/null || true

# Signal Layer
sudo systemctl stop signal-aggregator 2>/dev/null || true
sudo systemctl stop silver-signal-generator 2>/dev/null || true
sudo systemctl stop gold-signal-generator 2>/dev/null || true

# Data Layer
sudo systemctl stop timeframe-aggregator 2>/dev/null || true
sudo systemctl stop data-collector 2>/dev/null || true

echo -e "${RED}All services stopped.${NC}"
