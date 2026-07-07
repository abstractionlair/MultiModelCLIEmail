#!/usr/bin/env bash
set -euo pipefail

# run-role.sh - Launch AI tool in messaging role
#
# Usage: ./run-role.sh <role-name>
#
# Examples:
#   ./run-role.sh claude
#   ./run-role.sh gpt-5

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

CONFIG_DIR="$PROJECT_ROOT/config"
ROLES_DIR="$PROJECT_ROOT/roles"

# Check dependencies
if ! command -v jq &> /dev/null; then
    echo "Error: jq is required but not installed." >&2
    echo "Install with: brew install jq" >&2
    exit 1
fi

# Parse arguments
if [ $# -lt 1 ]; then
    echo "Usage: $0 <role-name>" >&2
    echo "" >&2
    echo "Launch an AI tool in a specific role for multi-model messaging." >&2
    echo "" >&2
    echo "Available roles:" >&2
    jq -r 'keys[]' "$CONFIG_DIR/role-config.json" | grep -v "coordinator\|monitor" | sed 's/^/  /' >&2
    exit 1
fi

ROLE_NAME="$1"

# Load configurations
ROLE_CONFIG_FILE="$CONFIG_DIR/role-config.json"
TOOL_CONFIG_FILE="$CONFIG_DIR/tool-config.json"

if [ ! -f "$ROLE_CONFIG_FILE" ]; then
    echo "Error: Role config not found: $ROLE_CONFIG_FILE" >&2
    exit 1
fi

if [ ! -f "$TOOL_CONFIG_FILE" ]; then
    echo "Error: Tool config not found: $TOOL_CONFIG_FILE" >&2
    exit 1
fi

# Look up role configuration
ROLE_DEF=$(jq -r --arg role "$ROLE_NAME" '.[$role] // empty' "$ROLE_CONFIG_FILE")
if [ -z "$ROLE_DEF" ]; then
    echo "Error: Unknown role: $ROLE_NAME" >&2
    echo "" >&2
    echo "Available roles:" >&2
    jq -r 'keys[]' "$ROLE_CONFIG_FILE" | grep -v "coordinator\|monitor" | sed 's/^/  /' >&2
    exit 1
fi

TOOL=$(echo "$ROLE_DEF" | jq -r '.tool')
MODEL=$(echo "$ROLE_DEF" | jq -r '.model // empty')
DESCRIPTION=$(echo "$ROLE_DEF" | jq -r '.description')

# Check if human role
if [ "$TOOL" = "human" ]; then
    echo "Error: Cannot launch human role '$ROLE_NAME' via this script" >&2
    echo "Use: mutt -f .messages/$ROLE_NAME" >&2
    exit 1
fi

# Look up tool configuration
TOOL_DEF=$(jq -r --arg tool "$TOOL" '.[$tool] // empty' "$TOOL_CONFIG_FILE")
if [ -z "$TOOL_DEF" ]; then
    echo "Error: Unknown tool: $TOOL" >&2
    exit 1
fi

CLI=$(echo "$TOOL_DEF" | jq -r '.cli')

# Verify CLI is installed
if ! command -v "$CLI" &> /dev/null; then
    echo "Error: $CLI is not installed or not in PATH" >&2
    exit 1
fi

# Build role file path
ROLE_FILE="$ROLES_DIR/role-$ROLE_NAME.md"
if [ ! -f "$ROLE_FILE" ]; then
    echo "Error: Role file not found: $ROLE_FILE" >&2
    exit 1
fi

# Build role context (system prompt)
build_role_context() {
    cat "$ROLE_FILE"
}

# Build initial task prompt
build_initial_task() {
    cat <<EOF
You are now active in the messaging system.

Check your mailbox for any messages and begin responding:

    msg poll --role $ROLE_NAME

If there are unread messages, read and respond to them.

Then enter your continuous monitoring loop as described in your role instructions.
EOF
}

# Change to project root for execution
cd "$PROJECT_ROOT"

# Show what we're launching
echo "=== Starting $TOOL in interactive mode ===" >&2
echo "Role: $ROLE_NAME" >&2
echo "Description: $DESCRIPTION" >&2
if [ -n "$MODEL" ]; then
    echo "Model: $MODEL" >&2
fi
echo "" >&2

# Execute based on tool (always interactive for messaging system)
case "$TOOL" in
    claude)
        # Claude: system prompt for role context + initial task message
        ROLE_CONTENT=$(build_role_context)
        INITIAL_TASK=$(build_initial_task)
        exec claude --dangerously-skip-permissions --model "$MODEL" --append-system-prompt "$ROLE_CONTENT" "$INITIAL_TASK"
        ;;

    codex)
        # Codex: combine role context + task in initial message
        COMBINED_MSG=$(cat <<EOF
$(build_role_context)

---

$(build_initial_task)
EOF
)
        exec codex --dangerously-bypass-approvals-and-sandbox -m "$MODEL" "$COMBINED_MSG"
        ;;

    gemini)
        # Gemini: combine role context + task
        COMBINED_MSG=$(cat <<EOF
$(build_role_context)

---

$(build_initial_task)
EOF
)
        exec gemini --yolo -m "$MODEL" -i "$COMBINED_MSG"
        ;;

    opencode)
        # OpenCode: combine role context + task
        COMBINED_MSG=$(cat <<EOF
$(build_role_context)

---

$(build_initial_task)
EOF
)
        exec opencode -m "$MODEL" -p "$COMBINED_MSG"
        ;;

    *)
        echo "Error: Unsupported tool: $TOOL" >&2
        exit 1
        ;;
esac
