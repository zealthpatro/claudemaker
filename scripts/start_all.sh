#!/bin/bash
#
# Start all trading system services in the correct order
#

set -e

GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}Starting Precious Metals Trading System...${NC}"

# Data Layer
echo "Starting data services..."
sudo systemctl start data-collector
sleep 2
sudo systemctl start timeframe-aggregator

# Signal Layer
echo "Starting signal generators..."
sleep 2
sudo systemctl start gold-signal-generator
sudo systemctl start silver-signal-generator
sleep 2
sudo systemctl start signal-aggregator

# Bot Layer
echo "Starting trading bots..."
sleep 2
sudo systemctl start bot-scalper
sudo systemctl start bot-day-trader
sudo systemctl start bot-swing
sudo systemctl start bot-position
sudo systemctl start bot-sniper

# Learning Layer
echo "Starting learning services..."
sleep 2
sudo systemctl start trade-analyzer
sudo systemctl start feedback-loop

echo ""
echo -e "${GREEN}All services started!${NC}"
echo ""
echo "Checking status..."
./scripts/status.sh
