#!/bin/bash
#
# Restart a specific service
#

if [ -z "$1" ]; then
    echo "Usage: $0 <service-name>"
    echo ""
    echo "Available services:"
    echo "  data-collector"
    echo "  timeframe-aggregator"
    echo "  gold-signal-generator"
    echo "  silver-signal-generator"
    echo "  signal-aggregator"
    echo "  bot-scalper"
    echo "  bot-day-trader"
    echo "  bot-swing"
    echo "  bot-position"
    echo "  bot-sniper"
    echo "  trade-analyzer"
    echo "  feedback-loop"
    exit 1
fi

SERVICE=$1

echo "Restarting $SERVICE..."
sudo systemctl restart $SERVICE

echo "Checking status..."
sleep 2
sudo systemctl status $SERVICE --no-pager
