#!/usr/bin/env bash
# Test sendmail to see what mutt sends

TESTFILE="/tmp/mutt-message-dump.txt"
cat > "$TESTFILE"

echo "=== RAW MESSAGE SAVED TO: $TESTFILE ===" >&2
echo "First 30 lines:" >&2
head -30 "$TESTFILE" >&2

exit 0
