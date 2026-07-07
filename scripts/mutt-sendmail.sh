#!/usr/bin/env bash
#
# Sendmail wrapper for mutt to use msg send
# Parses RFC-compliant email from stdin and sends via msg tool
#

# Get project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT" || exit 1

# Read the email message from stdin
MESSAGE=$(cat)

# Save to temp file for debugging
TMPFILE="/tmp/mutt-sendmail-debug-$$.txt"
echo "$MESSAGE" > "$TMPFILE"

# Unfold headers (join continuation lines that start with whitespace)
HEADERS=$(echo "$MESSAGE" | awk '/^$/{exit} {if(/^[ \t]/) {printf " %s", $0} else {if(NR>1) print ""; printf "%s", $0}} END{print ""}')

# Parse headers
FROM=$(echo "$HEADERS" | grep -i "^From:" | head -1 | sed 's/^[Ff]rom: *//; s/.*<//; s/>.*//; s/@.*//')

# Parse To: field - extract all role names
TO=$(echo "$HEADERS" | grep -i "^To:" | head -1 | grep -oE '[a-z0-9_-]+@multimodel\.local' | sed 's/@multimodel\.local//g' | paste -sd ',' -)

SUBJECT=$(echo "$HEADERS" | grep -i "^Subject:" | head -1 | sed 's/^[Ss]ubject: *//')
IN_REPLY_TO=$(echo "$HEADERS" | grep -i "^In-Reply-To:" | head -1 | sed 's/^[Ii]n-[Rr]eply-[Tt]o: *//')

# Extract body (everything after first blank line)
BODY=$(echo "$MESSAGE" | awk 'BEGIN{p=0} /^$/{p=1;next} p{print}')

# Debug output
echo "Debug: FROM='$FROM'" >&2
echo "Debug: TO='$TO'" >&2
echo "Debug: SUBJECT='$SUBJECT'" >&2
echo "Debug: Message saved to $TMPFILE" >&2

# Validate
if [[ -z "$FROM" ]]; then
    echo "Error: Could not parse From header" >&2
    echo "Debug file: $TMPFILE" >&2
    exit 1
fi

if [[ -z "$TO" ]]; then
    echo "Error: Could not parse To header" >&2
    echo "Debug file: $TMPFILE" >&2
    exit 1
fi

# Build msg send command
CMD="./scripts/msg send --from \"$FROM\" --to \"$TO\" --subject \"$SUBJECT\""

# Add reply-to if present
if [[ -n "$IN_REPLY_TO" ]]; then
    CMD="$CMD --reply-to \"$IN_REPLY_TO\""
fi

# Send the message
echo "$BODY" | eval $CMD
RESULT=$?

# Clean up debug file on success
if [[ $RESULT -eq 0 ]]; then
    rm -f "$TMPFILE"
fi

exit $RESULT
