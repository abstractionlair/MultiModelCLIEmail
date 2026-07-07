#!/usr/bin/env bash
#
# Launch mutt for coordinator role
#

# Get project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$PROJECT_ROOT" || {
    echo "Error: Could not change to project directory: $PROJECT_ROOT"
    exit 1
}

# Check if config file exists
if [[ ! -f "config/muttrc-coordinator" ]]; then
    echo "Error: config/muttrc-coordinator not found"
    exit 1
fi

# Check if maildir exists
if [[ ! -d ".messages/coordinator" ]]; then
    echo "Error: .messages/coordinator mailbox not found"
    exit 1
fi

echo "Starting mutt for coordinator role..."
echo "Mailbox: .messages/coordinator"
echo ""

# Launch mutt with custom config
mutt -F config/muttrc-coordinator
