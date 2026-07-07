# Quick Start: Multi-Model Conversation

Ready to continue the conversation from `multimodel_conversation_DAG.md` with full coding capabilities!

## Prerequisites

- `jq` installed: `brew install jq`
- One or more of these CLIs installed:
  - `claude` (Claude Code)
  - `codex` (OpenAI Codex)
  - `gemini` (Gemini CLI)
  - `opencode` (xAI OpenCode for Grok)

## Testing the System

### 1. Launch a Role (in a new terminal)

```bash
cd ~/projects/MultiModelCLIEmail

# Launch Claude
./scripts/run-role.sh claude

# Or GPT-5
./scripts/run-role.sh gpt-5

# Or Gemini
./scripts/run-role.sh gemini

# Or Grok
./scripts/run-role.sh grok
```

Each role will:
- Load its role instructions from `roles/role-<name>.md`
- Start in interactive mode
- Know about the previous conversation
- Have full coding capabilities

### 2. Send a Message (from another terminal or Mutt)

```bash
cd ~/projects/MultiModelCLIEmail

# Send a message
./scripts/msg send --from coordinator --to claude,gpt-5 \
  --subject "Continuing the conversation" \
  --content "Should we implement the evaluator ensemble first?"

# Or use Mutt for a better experience
mutt -f .messages/coordinator
```

### 3. Agent Receives and Responds

The agent running in the terminal from step 1 will:
1. See the message arrive (via `msg poll --wait`)
2. Read it
3. Respond (and possibly create code/specs/artifacts)
4. Loop back to waiting

### 4. Monitor All Traffic

In yet another terminal:

```bash
# Watch all messages
mutt -R -f .messages/monitor

# Or check messages via CLI
./scripts/msg poll --role monitor
```

## Full Multi-Model Setup

For the complete multi-model experience, open 5 terminals:

```bash
# Terminal 1: Your coordinator interface
mutt -f .messages/coordinator

# Terminal 2: Claude agent
./scripts/run-role.sh claude

# Terminal 3: GPT-5 agent  
./scripts/run-role.sh gpt-5

# Terminal 4: Gemini agent
./scripts/run-role.sh gemini

# Terminal 5: Monitor (observer)
mutt -R -f .messages/monitor
```

Then send a message from Terminal 1 to all agents, and watch the conversation unfold!

## Example Workflow

### Initial Kickoff

From coordinator:

```bash
./scripts/msg send --from coordinator --to claude,gpt-5,gemini,grok \
  --subject "Picking up where we left off" \
  --content "We discussed evaluator ensembles, quality-diversity search, and compositional intelligence. The conversation reached a point where we need to write code. Should we start with the evaluator infrastructure?"
```

### Agents Respond

Each agent (running in their terminal):
- Receives the message via `msg poll --wait`
- Reads and thinks about it
- Possibly creates artifacts (code, specs, designs)
- Sends a response using `msg reply` or `msg send`

### Models Talk to Each Other

Claude might respond:

```bash
msg send --from claude --to gpt-5,gemini \
  --subject "Evaluator design thoughts" \
  --artifacts "docs/proposed/evaluator-framework.md" \
  --content "I've outlined the conceptual framework. GPT-5, what do you think about the concrete architecture? Gemini, does this align with your 'pragmatic GA' vision?"
```

### Continue Naturally

The conversation continues with models responding to each other, you jumping in when needed, and all traffic visible in the monitor mailbox.

## Stopping

To stop an agent: `Ctrl-C` in its terminal

## Debugging

```bash
# Check messages for a role
./scripts/msg poll --role claude --all

# Read a specific message
./scripts/msg read --role claude <message-id>

# List available roles
./scripts/msg roles

# Check mailbox directories
ls -la .messages/claude/new/     # Unread
ls -la .messages/claude/cur/     # Read
ls -la .messages/monitor/new/    # All traffic
```

## Next Steps

- Import the previous conversation as email messages (optional)
- Create artifacts as the conversation progresses
- Use `--artifacts` to reference work products
- Build the evaluator ensemble together!

The goal: Continue the deep conversation about compositional intelligence, but now with the ability to actually implement and test the ideas.
