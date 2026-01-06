#!/bin/bash
#
# Check status of all trading system services
#

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

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

echo ""
echo "=== Precious Metals Trading System Status ==="
echo ""
printf "%-30s %-15s %-20s\n" "SERVICE" "STATUS" "UPTIME"
echo "--------------------------------------------------------------"

for service in "${SERVICES[@]}"; do
    status=$(systemctl is-active $service 2>/dev/null || echo "unknown")

    if [ "$status" == "active" ]; then
        color=$GREEN
        uptime=$(systemctl show $service --property=ActiveEnterTimestamp --value 2>/dev/null | cut -d' ' -f2- || echo "unknown")
    elif [ "$status" == "inactive" ]; then
        color=$YELLOW
        uptime="stopped"
    else
        color=$RED
        uptime="not installed"
    fi

    printf "${color}%-30s %-15s${NC} %-20s\n" "$service" "$status" "$uptime"
done

echo ""
echo "=== System Resources ==="
echo ""

# Memory usage
free -h | grep -E '^Mem:'

# Disk usage
df -h / | tail -1

# CPU load
uptime | awk -F'load average:' '{print "Load average:" $2}'

echo ""
