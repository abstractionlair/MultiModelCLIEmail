# DEPRECATED

This file describes the **old manual copy/paste protocol** used in the web chat interface that produced `multimodel_conversation_DAG.md`.

**This protocol is superseded by the file-based email system described in `DESIGN.md` and `README.md`.**

The new system uses:
- Standard email (Maildir format) instead of custom envelopes
- File-based messaging instead of copy/paste
- Persistent agents instead of one-shot
- Role-based addressing instead of model@{...}
- Full CLI tool capabilities instead of just chat

---

# Original Protocol (for reference)

Multi‑Model Messaging Protocol (MMSG v1)

Purpose
- Allow humans to relay messages between isolated model UIs (Claude Code, Codex, Gemini, OpenCode) using copy/paste.
- Keep replies structured and linkable so a CLI can reconstruct a DAG.

[... rest of original protocol ...]
