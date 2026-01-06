#!/bin/bash
#
# View logs for a service
#

if [ -z "$1" ]; then
    echo "Usage: $0 <service-name> [lines]"
    echo ""
    echo "Examples:"
    echo "  $0 bot-scalper        # Last 50 lines"
    echo "  $0 bot-scalper 100    # Last 100 lines"
    echo "  $0 bot-scalper -f     # Follow (tail -f)"
    exit 1
fi

SERVICE=$1
LINES=${2:-50}

if [ "$LINES" == "-f" ]; then
    echo "Following logs for $SERVICE (Ctrl+C to stop)..."
    journalctl -u $SERVICE -f
else
    echo "Last $LINES log lines for $SERVICE:"
    echo ""
    journalctl -u $SERVICE -n $LINES --no-pager
fi
