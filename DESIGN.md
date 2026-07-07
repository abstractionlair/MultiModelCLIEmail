# Multi-Model Messaging System: Design Document

## Problem Statement

### Original Problem (Web Chat Interface)

The `multimodel_conversation_DAG.md` conversation happened in a web chat interface where:
- Multiple AI models (GPT-5, Claude, Gemini, Grok) collaborated
- User manually copy/pasted messages between model UIs
- Custom `<<<MMSG:V1:...>>>` envelope format for structured messages
- Worked, but limited to chat - no code execution, file access, tests, etc.

See `PROTOCOL.md` for the old manual protocol.

### New Problem (CLI/TUI Coding Tools)

Enable similar multi-model collaboration, but in CLI/TUI coding environments where models can:
- Write and execute code
- Run tests and builds
- Read/edit files
- Use full capabilities of Claude Code, Codex, Gemini, OpenCode

**Key challenge**: These tools run in separate processes/machines and cannot directly communicate.

## Solution: Email-Based Messaging

### Core Insight

**Use standard email protocols (Maildir) instead of custom formats.**

This gives us:
1. **Existing tooling** - Mutt, mu, notmuch work out of the box
2. **Standard format** - RFC-compliant, well-understood
3. **Simple implementation** - Just files and directories
4. **Debuggable** - Easy to inspect messages
5. **Threading** - Email already has reply-to, references

### Architecture Decision Tree

**Q: How should models communicate?**
- ❌ HTTP/WebSocket - Requires server, complex
- ❌ Database - Overkill, needs infrastructure
- ❌ Shared memory - Doesn't work across machines
- ✅ Files - Simple, works locally and via sync

**Q: What file format?**
- ❌ Custom JSON queue - Reinventing the wheel
- ❌ SQLite - Overkill for message passing
- ✅ Maildir - Standard, atomic, tooling exists

**Q: How to organize messages?**
- ❌ Centralized queue - Single point of failure
- ❌ Peer-to-peer directories - Complex routing
- ✅ Per-role mailboxes - Clean, isolated, standard

**Q: How to identify participants?**
- ❌ By model (gpt-5, claude) - Ties to implementation
- ✅ By role (explorer-claude, reviewer-gpt5) - Flexible, maps to workflow

## Key Design Decisions

### 1. Roles, Not Models

**Decision**: Messages are between roles, not specific models.

**Rationale**:
- Same model can play different roles
- Roles can be reassigned to different models
- Maps to existing artifact workflow (spec-writer, implementer, etc.)
- Conversations are about responsibilities, not implementations

**Configuration**: `config/role-config.json`
```json
{
  "explorer-claude": {
    "tool": "claude",
    "model": "claude-sonnet-4-5"
  }
}
```

### 2. Standard Maildir Format

**Decision**: Use RFC-compliant email stored in Maildir directories.

**Structure**:
```
.messages/
  coordinator/
    new/      # Unread messages
    cur/      # Read messages  
    tmp/      # Delivery in progress
  explorer-claude/
    new/
    cur/
    tmp/
  ...
```

**Benefits**:
- Atomic delivery (tmp/ → new/)
- Clear state (new vs cur)
- Standard semantics
- Works with existing clients

### 3. Auto-BCC to Monitor

**Decision**: Automatically BCC all messages to a `monitor` mailbox.

**Rationale**:
- Separates participation from observation
- User can watch all traffic without being in every conversation
- Two interfaces: active (coordinator) + passive (monitor)
- Clean separation of concerns

**Implementation**: `msg send` automatically adds `monitor` to recipients unless explicitly excluded.

### 4. Glob Patterns for Artifacts

**Decision**: Reference artifacts using glob patterns in `X-Artifacts` header.

**Problem**: Artifacts move between state directories:
```
specs/proposed/auth.md → specs/todo/auth.md → specs/doing/auth.md → specs/done/auth.md
```

**Solution**: Use glob patterns:
```
X-Artifacts: specs/*/auth.md
```

**Benefits**:
- References survive state changes
- Clear intent (this specific artifact, any state)
- Simple to implement (use glob library)

### 5. Blocking Wait for Persistent Agents

**Decision**: `msg poll --wait` blocks until messages arrive.

**Breakthrough insight**: External `msg` command does the blocking, so the AI agent can loop indefinitely without finishing its response.

**Agent pattern**:
```python
while True:
    msg poll --role explorer-claude --wait  # Blocks efficiently
    # Process messages
    # Respond
    # Loop (never sends END token)
```

**Benefits**:
- True persistent agents (not one-shot)
- No busy-waiting (blocks in filesystem polling)
- Fast response (already running)
- User can interrupt (send message to role)
- Clean termination (Ctrl-C)

**Alternative considered**: External polling wrapper script
- More complex
- Another process to manage
- Agent pattern is simpler and self-contained

### 6. Fresh Context on Launch

**Decision**: Don't reload conversation history into tool context.

**Rationale**:
- Fresh context is often better
- Expensive to reconstruct
- Agents can search old messages if needed
- Role instructions mention this capability

**Implementation**: 
- Agent checks unread messages on launch
- Role instructions say "you can search older messages: `msg poll --all`"
- User controls when context matters

### 7. Manual Launch (MVP)

**Decision**: User manually launches roles in separate terminals.

**Alternatives considered**:
- Auto-launch daemon (spawns roles when messages arrive)
- One-shot mode (launch, process, exit)
- Idle timeout (exit after N minutes of inactivity)

**MVP choice**:
- Manual launch, stays alive
- User opens terminal per role
- Ctrl-C or close terminal to stop
- Simple, predictable

**Future**: Could add daemon/auto-launch as enhancement.

## Architecture

### Components

```
┌─────────────────────────────────────────────────┐
│  User Interfaces                                 │
│  ┌─────────────┐  ┌──────────────┐             │
│  │ coordinator │  │   monitor    │             │
│  │  (mutt)     │  │   (mutt -R)  │             │
│  │  Participant│  │   Observer   │             │
│  └─────────────┘  └──────────────┘             │
└─────────────────────────────────────────────────┘
                    │
                    ↓
┌─────────────────────────────────────────────────┐
│  Message Queue (.messages/ Maildir)              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │coordinator│ │  monitor │ │explorer- │        │
│  │new/cur/tmp│ │new/cur/tmp│ │claude ..│        │
│  └──────────┘ └──────────┘ └──────────┘        │
└─────────────────────────────────────────────────┘
                    │
                    ↓
┌─────────────────────────────────────────────────┐
│  Persistent Agents (Terminals)                   │
│  ┌──────────────┐  ┌──────────────┐            │
│  │ explorer-    │  │ explorer-    │            │
│  │   claude     │  │   gpt5       │            │
│  │ (Claude Code)│  │  (Codex)     │            │
│  └──────────────┘  └──────────────┘            │
└─────────────────────────────────────────────────┘
```

### Message Flow

1. **Send**:
   ```
   User/Agent → msg send → Recipient's new/ + Monitor's new/
   ```

2. **Poll (non-blocking)**:
   ```
   Agent → msg poll → Check new/ → Return immediately
   ```

3. **Poll (blocking)**:
   ```
   Agent → msg poll --wait → Loop checking new/ → Return when messages arrive
   ```

4. **Read**:
   ```
   Agent → msg read → Parse email from new/ or cur/
   ```

5. **Reply**:
   ```
   Agent → msg reply → Create new message with In-Reply-To header → Deliver
   ```

### Message Format

Standard RFC-compliant email:

```
From: explorer-claude@multimodel.local
To: coordinator@multimodel.local, explorer-gpt5@multimodel.local
Cc: explorer-gemini@multimodel.local
Subject: Evaluator design thoughts
Date: Sat, 02 Nov 2025 19:23:45 -0400
Message-ID: <msg-7369bb97-39f8-4f29-a913-936227cd22db@multimodel.local>
In-Reply-To: <msg-abc123@multimodel.local>
References: <msg-aaa111@multimodel.local> <msg-abc123@multimodel.local>
X-Role: explorer-claude
X-Model: claude-sonnet-4-5-20250929
X-Thinking-Mode: extended
X-Artifacts: specs/*/evaluator.md, code/eval.py

I think evaluation infrastructure is indeed the critical path...

[Message body]
```

**Standard headers**:
- From/To/Cc/Subject/Date - RFC 2822
- Message-ID - Unique identifier
- In-Reply-To/References - Threading (creates DAG)

**Custom headers** (X-prefixed):
- X-Role - Sender's role
- X-Model - Model used (informational)
- X-Artifacts - Artifact paths (glob patterns)
- X-Thinking-Mode / X-Reasoning-Effort - Model parameters

### Threading (DAG Structure)

Email's `In-Reply-To` and `References` headers naturally create a DAG:

```
                    msg-001 (initial question)
                       /              \
                      /                \
            msg-002 (claude)      msg-003 (gpt5)
                    |                   |
                    |                   |
            msg-004 (response)    msg-005 (response)
                       \              /
                        \            /
                      msg-006 (synthesis)
```

**No explicit "thread" concept** - topology emerges from reply chains.

**Future**: Could support multiple parents in `In-Reply-To` for true DAG (not just tree).

## Persistent Agent Lifecycle

### Terminal Setup

```bash
# Terminal 1: Your participant interface
mutt -f .messages/coordinator

# Terminal 2: Claude explorer (persistent)
./scripts/run-role.sh -i explorer-claude

# Terminal 3: GPT-5 explorer (persistent)
./scripts/run-role.sh -i explorer-gpt5

# Terminal 4: Your observer interface
mutt -R -f .messages/monitor
```

### Agent Lifecycle

```
┌─────────────────────────────────────────────┐
│ Launch: ./scripts/run-role.sh -i explorer-claude │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ Initialization                               │
│ - Load role instructions                     │
│ - Check for existing unread messages         │
│ - Process any backlog                        │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ Enter Wait Loop                              │
│                                              │
│ while True:                                  │
│   msg poll --role explorer-claude --wait    │
│   # ↑ Blocks here (efficient waiting)       │
│                                              │
│   # Messages arrived!                        │
│   for message in new_messages:              │
│     read_and_process(message)               │
│     respond_if_appropriate()                │
│                                              │
│   # Loop (no END token, stays alive)        │
└─────────────────────────────────────────────┘
                    ↑
                    └──────────────┐
                                   │
┌──────────────────────────────────┴──────────┐
│ Termination                                  │
│ - User sends stop message                    │
│ - User presses Ctrl-C                        │
│ - User closes terminal                       │
└─────────────────────────────────────────────┘
```

### Why This Works

**Key insight**: The agent never finishes its response. Each time it calls `msg poll --wait`, it's a Bash tool invocation that blocks. When it returns, the agent processes messages and loops back to another `msg poll --wait` call. **The response never ends**, so the agent stays alive.

**User interaction**: User can still send messages to the agent's role mailbox. Agent sees them on next poll.

**Resource efficiency**: Blocking in `msg poll --wait` (filesystem polling with sleep) is efficient - no busy-waiting.

## Comparison to Old Protocol

| Aspect | Old (PROTOCOL.md) | New (This System) |
|--------|-------------------|-------------------|
| **Transport** | Manual copy/paste | File-based (Maildir) |
| **Format** | Custom `<<<MMSG:V1>>>` | Standard RFC email |
| **Envelope** | Custom markers | Email headers |
| **Threading** | Manual `parents` field | `In-Reply-To` / `References` |
| **Tooling** | None (manual) | Mutt, msg CLI |
| **Capabilities** | Chat only | Full CLI tool features |
| **Participants** | model@{...} | Roles (configurable) |
| **Lifecycle** | One-shot per paste | Persistent agents |
| **Monitoring** | Manual | Auto-BCC to monitor |
| **Debugging** | Text inspection | Standard email tools |

## Future Enhancements

### Near-Term

1. **Launcher script** (`run-role.sh`)
   - Load role instructions
   - Launch appropriate CLI tool
   - Pass initial context

2. **Mutt config helpers**
   - Shell scripts to launch Mutt with correct settings
   - Key bindings for common operations

3. **Artifact glob resolver**
   - Helper to expand `specs/*/auth.md` to actual path
   - `msg artifacts <msg-id>` to list/open artifacts

4. **Additional role files**
   - explorer-gpt5, explorer-gemini, explorer-grok
   - Specialized roles (evaluator, synthesizer, critic)

### Medium-Term

5. **Workflow integration**
   - Review request/response messages
   - Artifact state change notifications
   - Integration with existing workflow scripts

6. **Auto-launch daemon** (optional)
   - Monitor mailboxes
   - Spawn roles when messages arrive
   - Idle timeout for resource management

7. **Rich threading visualization**
   - Generate DAG from email threads
   - GraphViz or similar output
   - Markdown conversation summaries

### Long-Term

8. **Cross-machine sync**
   - Dropbox/iCloud/Drive sync for `.messages/`
   - Email transport as fallback
   - Conflict resolution

9. **Security/auth**
   - Message signing (PGP)
   - Access control for roles
   - Audit logging

10. **Performance**
    - Indexing (mu, notmuch)
    - Search capabilities
    - Archive management

## Design Validation

### Does It Solve the Original Problem?

✅ **Multi-model collaboration**: Yes - roles can message each other

✅ **Full CLI capabilities**: Yes - agents run in full coding environments

✅ **Persistent agents**: Yes - `--wait` enables continuous operation

✅ **User observation**: Yes - monitor mailbox + Mutt

✅ **User participation**: Yes - coordinator role + Mutt

✅ **Threading/DAG**: Yes - email In-Reply-To/References

✅ **Debuggable**: Yes - standard email format, easy inspection

### What Did We Learn?

1. **Standard formats win**: Email gave us threading, tooling, debugging for free

2. **Files are simple**: No server, no network, just files and directories

3. **Blocking is elegant**: `--wait` makes persistent agents trivial

4. **Roles > Models**: Flexibility to reassign, maps to workflows

5. **Two interfaces**: Participant + observer is powerful pattern

6. **Globs for lifecycle**: Artifacts move, globs keep references valid

## Conclusion

This system provides a foundation for multi-model collaboration in CLI/TUI coding environments. By using standard email protocols and file-based messaging, we get:

- **Simplicity**: Just files, no infrastructure
- **Tooling**: Mutt and email clients work out of the box
- **Persistence**: Agents run continuously with `--wait`
- **Flexibility**: Roles are configurable and reassignable
- **Debuggability**: Standard format, easy to inspect
- **Extensibility**: Clear path to workflow integration

The old PROTOCOL.md (manual copy/paste) is superseded by this automated, file-based system.
