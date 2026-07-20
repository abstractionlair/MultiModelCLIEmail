# Multi-Model Messaging System

A role-based messaging system for multi-model AI collaboration in CLI/TUI coding environments.

## Overview

This project enables AI models running in different CLI tools (Claude Code, OpenAI Codex, Gemini, OpenCode) to communicate using the Maildir format and local storage.

**Key insight**: Use a standard email storage format (Maildir, local files in the project) and you can use existing email clients like Mutt to monitor agent communications and communicate with them!

**For architecture, design decisions, and comparison to the old protocol, see [DESIGN.md](DESIGN.md).**

## Repository Layout

This repository contains two separate projects sharing a common root:

### Multi-Model CLI "Email" System (main project)

Note: There isn't any actual _email_ here, no mail transport agent that sends or receives over the internet.
There's a file with "sendmail" in the name which reads and writes local files in the project and allowed me to use Mutt.
This project uses the Maildir _format_ for agents to write and read messages to and from each other via a _local_ project directory.


The email-based messaging system for AI model collaboration. Core files:

| Path | Purpose |
|------|---------|
| `scripts/msg` | Main CLI tool for send/poll/read/reply over Maildir |
| `mm.py` | Multi-model collaboration CLI (graph-based sessions) |
| `config/` | Role and tool configuration (Maildir mailboxes) |
| `roles/` | Role instruction files for AI agents |
| `sessions/` | Session data (JSONL graph storage) |
| `.messages/` | Maildir mailboxes — includes a committed archive of messages from the project's own development, plus new messages at runtime |
| `docs/` | System documentation and integration specs |
| `attic/` | Early artifacts kept for the record — `main.py` is a pre-system sketch from the planning conversation; it was never functional (placeholder keys, and a literal `\n` in a pasted comment leaves its DAG undefined) |
| `DESIGN.md`, `PROTOCOL.md` | Architecture and protocol docs |
| `QUICKSTART.md` | Getting-started guide |

### LLM Evaluator Experiment (`code/` and `tests/`)

A separate experiment for evaluating LLM output quality using pairwise comparison and quality-diversity search. This project lives entirely within `code/` and `tests/` and is unrelated to the email messaging system. Key modules: evaluator framework, judge pool ensemble, mutation strategies, calibration monitoring, and QD search.

## Quick Start

```bash
# List available roles
./scripts/msg roles

# Send a message
./scripts/msg send --from coordinator --to explorer-claude \
  --subject "Question" --content "What do you think?"

# Check for messages
./scripts/msg poll --role explorer-claude

# Read a message
./scripts/msg read --role explorer-claude <message-id>

# Use Mutt to read/send messages
mutt -f .messages/coordinator
```

## Architecture

### Roles (Not Models)

Messages are between **roles**, not specific models:
- `coordinator` - You (human facilitator)
- `monitor` - Observer (auto-BCC'd on all messages)
- `explorer-claude`, `explorer-gpt5`, `explorer-gemini`, `explorer-grok` - AI explorers

Roles can be reassigned to different models via `config/role-config.json`.

### Maildir Format

Standard email directory structure:
```
.messages/
  coordinator/
    new/      # Unread
    cur/      # Read
    tmp/      # Delivery
  monitor/    # BCC copy of ALL messages
  explorer-claude/
  ...
```

### Message Format

RFC-compliant email with custom headers:

```
From: explorer-claude@multimodel.local
To: coordinator@multimodel.local
Subject: Design thoughts
X-Role: explorer-claude
X-Artifacts: specs/*/auth.md
In-Reply-To: <msg-abc@multimodel.local>

[Content...]
```

### Artifact References

Use glob patterns so links survive state transitions:
```
X-Artifacts: specs/*/auth.md
```

This works whether the spec is in `proposed/`, `doing/`, or `done/`.

## Two Interfaces for You

**1. Participant** (`coordinator` mailbox):
- Your active inbox/outbox
- Send and receive messages
- Engage in conversations

**2. Observer** (`monitor` mailbox):
- Auto-BCC'd on ALL messages
- Watch entire conversation flow
- Read-only monitoring

Open both in separate terminals:
```bash
# Terminal 1: Active participation
mutt -f .messages/coordinator

# Terminal 2: Passive observation
mutt -R -f .messages/monitor
```

## CLI Commands

### msg send
```bash
msg send --from <role> --to <roles> --subject "..." --content "..."
  [--cc <roles>] [--reply-to <msg-id>] [--artifacts <paths>]
```

### msg poll
```bash
msg poll --role <role> [--all] [--wait] [--timeout N]
```

**Flags:**
- `--all`: Show all messages (cur/ and new/), not just unread
- `--wait`: Block until messages arrive (for persistent agents)
- `--timeout N`: Optional timeout in seconds for --wait mode (default: wait forever)

### msg read
```bash
msg read --role <role> <message-id> [--headers]
```

**Note**: Messages are **automatically marked as read** when you read them (moved from `new/` to `cur/`).

### msg reply
```bash
msg reply --from <role> <message-id> [--to <roles>] [--content "..."]
```

**Note**: Replying to a message automatically marks it as read.

## Message State Management

Messages are stored in standard Maildir format:
- **new/** - Unread messages
- **cur/** - Read messages
- **tmp/** - Temporary (during delivery)

### Automatic State Transitions

- **Read**: `msg read` automatically marks messages as read (moves from `new/` to `cur/`)
- **Reply**: `msg reply` automatically marks the original message as read

### Advanced Queries with mu

The `mu` email indexer is available for complex searches:

```bash
# Search for messages from coordinator about evaluators
mu find from:coordinator subject:evaluator maildir:/.messages/claude

# Find all messages from gpt-5
mu find from:gpt-5 maildir:/.messages/claude

# Find messages with artifacts
mu find 'x-artifacts:*' maildir:/.messages/claude

# Complex query: unread messages from last week
mu find date:7d..now flag:unread maildir:/.messages/claude/new
```

The `msg` commands handle common cases. Use `mu` when you need powerful search/filtering.

## Use Cases

### A. Multi-Model Conversations

Have exploratory conversations where models collaborate:
- You or any model initiates
- Models respond to each other directly
- Natural DAG emerges via reply-to
- You observe and/or participate

Unlike pure chat, models can:
- Write code
- Run tests
- Read/edit files
- All the things CLI tools can do

### B. Workflow Automation (Future)

Integrate with artifact workflows:
- Writer finishes → sends review request
- Reviewer polls → writes review → responds
- Blocking or async modes

## Persistent Agents

The `--wait` flag enables true persistent agents that run continuously:

### Agent Pattern

```python
# Agent runs indefinitely in interactive mode
while True:
    # Block until messages arrive
    msg poll --role explorer-claude --wait

    # Process messages
    # Respond as needed

    # Loop (never ends response)
```

### How It Works

1. **Launch interactive session**: `./scripts/run-role.sh -i explorer-claude`
2. **Agent initialization**: Checks for existing unread messages
3. **Enter wait loop**: Blocks on `msg poll --wait`
4. **Message arrives**: Poll returns with messages
5. **Process and respond**: Agent reads, thinks, responds
6. **Return to waiting**: Loop back to step 3
7. **Termination**: Ctrl-C or close terminal

### Benefits

- Truly persistent agents (not one-shot)
- No resource waste (blocks efficiently)
- Fast response (already running)
- User can still interrupt (send message to role)
- Clean lifecycle (Ctrl-C to stop)

### Example

```
Terminal 2: Claude Explorer
$ ./scripts/run-role.sh -i explorer-claude

Starting continuous monitoring for role: explorer-claude
Checking for existing messages...
No unread messages.
Waiting for messages... (blocking)

[... user sends message ...]

Received 1 message:
  From: coordinator
  Subject: Design question

Reading message...
[thinks and responds]

Sent reply: <msg-abc123>
Waiting for messages... (blocking)

[continues indefinitely until Ctrl-C]
```

## Using Mutt

### Quick Start (Recommended)

Use the provided launcher scripts with preconfigured settings:

```bash
# Coordinator mailbox (your active inbox)
./scripts/mutt-coordinator.sh

# Monitor mailbox (read-only observer)
./scripts/mutt-monitor.sh
```

These scripts use project-local configuration files (`config/muttrc-coordinator` and `config/muttrc-monitor`) with proper threading, colors, and UI settings.

### Manual Launch (Alternative)

If you prefer to configure your own `~/.muttrc`:
```
set folder="~/Projects/MultiModelCLIEmail/.messages"
set spoolfile="+coordinator"
mailboxes +coordinator +monitor +claude +gpt-5 +gemini +grok
set sort=threads
```

Then:
```bash
mutt -f .messages/coordinator  # Your active mailbox
mutt -R -f .messages/monitor   # Observer mode (read-only)
```

## Design Decisions

**Why Maildir?**
- Standard, battle-tested format
- Works with existing tools (Mutt, mu, notmuch)
- Simple (just files)
- Atomic, debuggable

**Why auto-BCC to monitor?**
- Separates participation from observation
- You can watch all traffic without being in every conversation
- Clean separation of concerns

**Why roles not models?**
- Same model can play different roles
- Roles can be reassigned
- Maps to existing workflow concepts

**Why glob patterns for artifacts?**
- Artifacts move as state changes (`proposed/` → `doing/` → `done/`)
- Globs keep references valid

## Testing

Run tests with `unittest` (not pytest — the `code/` directory shadows Python's stdlib `code` module which breaks pytest collection):

```bash
python3 -m unittest discover -s tests -v
```

Alternatively, run a single test file:

```bash
python3 -m unittest tests/test_evaluators.py -v
```

## Status

**Working:**
- [x] Maildir structure
- [x] Basic CLI (send, poll, read, reply)
- [x] Auto-BCC to monitor
- [x] Standard email format
- [x] Glob artifact references
- [x] **Blocking wait** (`msg poll --wait`) for persistent agents
- [x] Role instruction files (example: explorer-claude)

**TODO:**
- [ ] Launcher script (run-role.sh)
- [ ] Mutt configuration helpers
- [ ] Artifact glob resolver helper
- [ ] Integration with workflow system
- [ ] Additional role files (gpt5, gemini, grok)

## Next Steps

Try it out! Send a message from coordinator to an explorer role, then see it appear in monitor.

## Provenance

The thesis this repo serves — compositional intelligence, conversations arranged as a DAG, a market-of-agents lens on multi-model work — is mine; I brought it to the models, not the other way around. So is the repo concept itself: inter-CLI messaging, email for models. One exception worth crediting: the quality-diversity search in the evaluator experiment was GPT-5's proposal, which I adopted after making it justify itself. Essentially all of the code was written and cross-reviewed by a four-model team, with me acting as coordinator rather than author. The committed Maildir archive in `.messages/` is the raw record of that collaboration — the development traffic is published in the same format the system exists to carry.
