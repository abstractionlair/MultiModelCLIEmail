#!/usr/bin/env bash
#
# Launch mutt for monitor role (read-only observer)
#

# Get project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$PROJECT_ROOT" || {
    echo "Error: Could not change to project directory: $PROJECT_ROOT"
    exit 1
}

# Check if config file exists
if [[ ! -f "config/muttrc-monitor" ]]; then
    echo "Error: config/muttrc-monitor not found"
    exit 1
fi

# Check if maildir exists
if [[ ! -d ".messages/monitor" ]]; then
    echo "Error: .messages/monitor mailbox not found"
    exit 1
fi

echo "Starting mutt for monitor role (READ-ONLY)..."
echo "Mailbox: .messages/monitor"
echo "Note: This is a read-only view of all conversation traffic."
echo ""

# Launch mutt in read-only mode with custom config
mutt -R -F config/muttrc-monitor
