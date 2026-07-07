#!/usr/bin/env python3
import argparse
import json
import os
import sys
import textwrap
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict


SESSIONS_DIR = os.path.join(os.getcwd(), "sessions")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def ensure_sessions_dir():
    os.makedirs(SESSIONS_DIR, exist_ok=True)


def session_path(name: str) -> str:
    ensure_sessions_dir()
    return os.path.join(SESSIONS_DIR, name)


def graph_path(name: str) -> str:
    return os.path.join(session_path(name), "graph.jsonl")


def meta_path(name: str) -> str:
    return os.path.join(session_path(name), "meta.json")


def load_graph(name: str):
    path = graph_path(name)
    if not os.path.exists(path):
        return []
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                # skip malformed line
                continue
    return items


def append_graph(name: str, obj: dict):
    os.makedirs(session_path(name), exist_ok=True)
    with open(graph_path(name), "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def short_id(uid: str, n: int = 8) -> str:
    return uid.replace("-", "")[:n]


def read_stdin_or_file(path: Optional[str]) -> str:
    if path and path != "-":
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    # read stdin until EOF
    data = sys.stdin.read()
    return data


def resolve_ids(nodes: List[Dict], prefixes: List[str]) -> List[str]:
    resolved = []
    for pref in prefixes:
        matched = [n for n in nodes if n.get("id", "").replace("-", "").startswith(pref)]
        if not matched:
            raise SystemExit(f"No node with id starting with {pref}")
        if len(matched) > 1:
            raise SystemExit(f"Ambiguous id prefix {pref} matches {len(matched)} nodes")
        resolved.append(matched[0]["id"])
    return resolved


def cmd_init(args):
    name = args.name
    sp = session_path(name)
    if os.path.exists(sp):
        print(f"Session already exists: {sp}")
        return
    os.makedirs(sp, exist_ok=True)
    # write meta
    meta = {
        "id": name,
        "created": now_iso(),
        "title": args.title or name,
        "models": [],
        "cid": str(uuid.uuid4()),
    }
    with open(meta_path(name), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    # touch graph
    open(graph_path(name), "a").close()
    print(f"Initialized session at {sp}")


def new_node(role: str, model: Optional[str], content: str, parents: Optional[List[str]], ntype: str = "message", title: Optional[str] = None, tags: Optional[List[str]] = None, node_id: Optional[str] = None, to: Optional[str] = None, cid: Optional[str] = None):
    uid = node_id or str(uuid.uuid4())
    node = {
        "id": uid,
        "ts": now_iso(),
        "role": role,  # user | model | system | tool
        "model": model,  # e.g., gpt-5 | claude | gemini | grok | None
        "type": ntype,  # message | summary | evaluation | prompt
        "title": title,
        "content": content,
        "parents": parents or [],
        "tags": tags or [],
        "metrics": {},
        "to": to,
        "cid": cid,
    }
    return node


def find_latest_user_node(nodes: List[Dict]) -> Optional[Dict]:
    for node in reversed(nodes):
        if node.get("role") == "user":
            return node
    return None


def cmd_add(args):
    name = args.session
    nodes = load_graph(name)
    content = read_stdin_or_file(args.from_path)
    parents = args.parents or []
    node = new_node(role=args.role, model=args.model, content=content, parents=parents, ntype=args.type, title=args.title)
    append_graph(name, node)
    print(f"Added node {short_id(node['id'])} ({args.role}{'/'+args.model if args.model else ''}) with {len(content)} chars")


FANOUT_HEADER = """
You are part of a multi-model collaboration. Multiple distinct LLMs will respond independently.
Please provide your best, self-contained response. Be concise and structured.

Instructions:
- Treat your output as a durable artifact; include context needed for a reader.
- Focus on reasoning, tradeoffs, and concrete next actions.
- If evaluating, use relative ranking and justification.
- If proposing, include 2–3 alternatives and selection criteria.
""".strip()


def build_model_wrapper(model: str, title: Optional[str], base_prompt: str) -> str:
    banner = f"=== {model.upper()} | {title or 'Task'} ==="
    return textwrap.dedent(f"""
    {banner}

    {FANOUT_HEADER}

    Task/Context:
    {base_prompt}

    Output Guidelines:
    - Use short sections with headers where helpful.
    - Avoid fluff. Provide concrete points and decisions.
    - End with a crisp summary and next steps.
    """).strip()


def cmd_fanout(args):
    name = args.session
    base = read_stdin_or_file(args.input)
    nodes = load_graph(name)
    parent_ids = []
    # record the user prompt as a node
    user_node = new_node(role="user", model=None, content=base, parents=args.parents or [], ntype="prompt", title=args.title)
    append_graph(name, user_node)
    parent_ids.append(user_node["id"])

    models = args.models
    print("# Copy these prompts into each model chat:\n")
    for m in models:
        wrapper = build_model_wrapper(m, args.title, base)
        print(wrapper)
        print("\n---\n")
    print("# When you have responses, use the ingest command to add them.")
    print(f"Parent node id: {short_id(user_node['id'])} (full: {user_node['id']})")


# ---------- MMSG v1 (copy/paste envelope) ----------
MMSG_BEGIN = "<<<MMSG:V1:BEGIN>>>"
MMSG_BODY = "<<<MMSG:V1:BODY>>>"
MMSG_END = "<<<MMSG:V1:END>>>"


def load_meta(name: str) -> Dict:
    try:
        with open(meta_path(name), "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def compose_envelope(cid: str, mid: str, from_actor: str, to_actor: str, mtype: str, subject: str, body: str, parents: Optional[List[str]] = None) -> str:
    parents_line = ", ".join(parents or [])
    header = [
        MMSG_BEGIN,
        f"cid: {cid}",
        f"mid: {mid}",
        f"from: {from_actor}",
        f"to: {to_actor}",
        f"type: {mtype}",
        f"parents: {parents_line}",
        f"subject: {subject or ''}",
        MMSG_BODY,
    ]
    footer = [MMSG_END]
    # brief reminder for models at top of body
    guide = (
        "You are participating in a multi-model collaboration. Reply by preserving the header, "
        "changing only mid/from/to/parents/type as appropriate, and put your response in the BODY."
    )
    return "\n".join(header + [guide, "", body, ""] + footer)


def parse_envelope(text: str) -> Optional[Dict]:
    try:
        start = text.index(MMSG_BEGIN)
        body_sep = text.index(MMSG_BODY, start)
        end = text.index(MMSG_END, body_sep)
    except ValueError:
        return None
    header_block = text[start:body_sep].splitlines()[1:]  # skip BEGIN
    body = text[body_sep + len(MMSG_BODY): end]
    kv = {}
    for line in header_block:
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            kv[k.strip()] = v.strip()
    parents_raw = kv.get("parents", "").strip()
    parents = [p.strip() for p in parents_raw.split(',') if p.strip()]
    env = {
        "cid": kv.get("cid"),
        "mid": kv.get("mid"),
        "from": kv.get("from"),
        "to": kv.get("to"),
        "type": kv.get("type"),
        "subject": kv.get("subject"),
        "parents": parents,
        "body": body.strip(),
    }
    return env


def cmd_compose(args):
    name = args.session
    meta = load_meta(name)
    cid = meta.get("cid") or str(uuid.uuid4())
    # optional parent id resolution
    nodes = load_graph(name)
    parents = resolve_ids(nodes, args.parents) if args.parents else []
    body = read_stdin_or_file(args.body)
    from_actor = args.from_actor or "user@cli"
    subject = args.subject or ""
    # create an internal record for each outgoing message
    for target in args.to:
        mid = str(uuid.uuid4())
        to_actor = f"model@{target}"
        env = compose_envelope(cid, mid, from_actor, to_actor, args.type, subject, body, parents)
        # store the outgoing as a node with id=mid
        node = new_node(
            role="user",
            model=None,
            content=body,
            parents=parents,
            ntype=args.type,
            title=subject,
            node_id=mid,
            to=to_actor,
            cid=cid,
        )
        append_graph(name, node)
        banner = f"Copy into {target.upper()} (subject: {subject}):"
        print(banner)
        print(env)
        print("\n---\n")


def cmd_ingest_msg(args):
    name = args.session
    raw = read_stdin_or_file(args.from_path)
    env = parse_envelope(raw)
    if not env:
        print("Could not find a valid MMSG v1 envelope in input.")
        return 1
    meta = load_meta(name)
    if env.get("cid") and meta.get("cid") and env["cid"] != meta["cid"]:
        print("Warning: cid mismatch with session; ingesting anyway.")
    # deduce role/model from 'from'
    from_field = env.get("from") or ""
    role = "model" if "model@" in from_field else "user"
    model = None
    if role == "model":
        try:
            model = from_field.split("model@", 1)[1].strip()
        except Exception:
            model = None
    node = new_node(
        role=role,
        model=model,
        content=env.get("body") or "",
        parents=env.get("parents") or [],
        ntype=env.get("type") or "message",
        title=env.get("subject"),
        node_id=env.get("mid"),
        to=env.get("to"),
        cid=env.get("cid"),
    )
    append_graph(name, node)
    print(f"Ingested message {short_id(node['id'])} from {from_field or 'unknown'}")
    return 0


def build_rank_prompt(title: Optional[str], criteria: List[str], candidates: List[Dict]) -> str:
    crit_line = ", ".join(criteria)
    parts = [
        "You are serving as an evaluator in a multi-model collaboration.",
        f"Rank the following {len(candidates)} candidate responses by: {crit_line}.",
        "Provide:",
        "1) A concise ranked list (best → worst) with 1–2 sentence justifications.",
        "2) A JSON object {\"ranking\": [ids...], \"notes\": {id: reason}}.",
        "Be strict about coherence and usefulness; reward novel but viable ideas.",
        "Candidates:",
    ]
    for i, c in enumerate(candidates, start=1):
        label = short_id(c["id"]) + (f"/{c.get('model')}" if c.get("model") else "")
        parts.append(f"\n=== C{i}: {label} ===\n{c.get('content','').strip()}\n")
    return "\n".join(parts)


def cmd_rank(args):
    name = args.session
    nodes = load_graph(name)
    ids = resolve_ids(nodes, args.candidates)
    cand_nodes = [n for n in nodes if n.get("id") in ids]
    prompt = build_rank_prompt(args.title, args.criteria, cand_nodes)
    print("# Copy this evaluator prompt into each selected model chat:\n")
    for m in args.models:
        wrapper = build_model_wrapper(m, args.title or "Rank candidates", prompt)
        print(wrapper)
        print("\n---\n")


def cmd_ingest(args):
    name = args.session
    content = read_stdin_or_file(args.from_path)
    nodes = load_graph(name)
    parents = args.parents or []
    if not parents:
        latest_user = find_latest_user_node(nodes)
        if latest_user:
            parents = [latest_user["id"]]
    node = new_node(role="model", model=args.model, content=content, parents=parents, ntype="message", title=args.title)
    append_graph(name, node)
    print(f"Ingested response as node {short_id(node['id'])} for model {args.model}")


def cmd_view(args):
    name = args.session
    nodes = load_graph(name)
    if not nodes:
        print("No nodes yet.")
        return
    print(f"Session: {name} | {len(nodes)} nodes")
    for i, n in enumerate(nodes, start=1):
        first_line = (n.get("content") or "").strip().splitlines()[0] if n.get("content") else ""
        role = n.get("role")
        model = n.get("model")
        nid = short_id(n["id"]) 
        parent_short = ",".join(short_id(p) for p in n.get("parents", [])) or "-"
        to_field = n.get("to") or ""
        to_disp = f" -> {to_field}" if to_field else ""
        print(f"[{i:03}] {nid} {role}{'/' + model if model else ''}{to_disp} <- {parent_short} | {first_line[:80]}")


def cmd_export_md(args):
    name = args.session
    nodes = load_graph(name)
    # stable sort by timestamp then by insertion
    nodes.sort(key=lambda n: n.get("ts", ""))
    for n in nodes:
        role = n.get("role")
        model = n.get("model") or "User"
        title = n.get("title")
        header = f"{model}:" if role != "user" else "User:"
        print(f"{header} {(title or '').strip()}")
        print((n.get("content") or "").rstrip())
        print()


def build_parser():
    p = argparse.ArgumentParser(description="Multi-model collaboration CLI (copy/paste oriented)")
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("init", help="Create a new session")
    sp.add_argument("name", help="Session name")
    sp.add_argument("--title", help="Optional title", default=None)
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("add", help="Add a node from stdin or file")
    sp.add_argument("session", help="Session name")
    sp.add_argument("--role", choices=["user", "model", "system", "tool"], required=True)
    sp.add_argument("--model", help="Model name if role=model", default=None)
    sp.add_argument("--type", help="Node type", default="message")
    sp.add_argument("--title", help="Optional title", default=None)
    sp.add_argument("--parents", nargs="*", help="Parent node ids", default=None)
    sp.add_argument("--from", dest="from_path", help="Path to content or '-' for stdin", default="-")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("fanout", help="Record a prompt and print per-model wrappers")
    sp.add_argument("session", help="Session name")
    sp.add_argument("--models", nargs="+", required=True, help="Model names, e.g., gpt-5 claude gemini grok")
    sp.add_argument("--title", help="Short title for this round", default=None)
    sp.add_argument("--parents", nargs="*", help="Parent node ids", default=None)
    sp.add_argument("--input", help="Path to base prompt or '-' for stdin", default="-")
    sp.set_defaults(func=cmd_fanout)

    sp = sub.add_parser("ingest", help="Add a model response from stdin or file")
    sp.add_argument("session", help="Session name")
    sp.add_argument("--model", required=True, help="Model name, e.g., gpt-5, claude")
    sp.add_argument("--title", help="Optional title", default=None)
    sp.add_argument("--parents", nargs="*", help="Parent node ids (defaults to latest user node)", default=None)
    sp.add_argument("--from", dest="from_path", help="Path to response or '-' for stdin", default="-")
    sp.set_defaults(func=cmd_ingest)

    sp = sub.add_parser("view", help="List nodes and edges")
    sp.add_argument("session", help="Session name")
    sp.set_defaults(func=cmd_view)

    sp = sub.add_parser("export-md", help="Export conversation to Markdown")
    sp.add_argument("session", help="Session name")
    sp.set_defaults(func=cmd_export_md)

    sp = sub.add_parser("rank", help="Generate evaluator prompts to rank candidate nodes")
    sp.add_argument("session", help="Session name")
    sp.add_argument("--models", nargs="+", required=True, help="Evaluator models")
    sp.add_argument("--criteria", nargs="+", required=True, help="Ranking criteria, e.g., coherence novelty usefulness")
    sp.add_argument("--candidates", nargs="+", required=True, help="Candidate node id prefixes")
    sp.add_argument("--title", help="Optional title", default=None)
    sp.set_defaults(func=cmd_rank)

    sp = sub.add_parser("compose", help="Compose MMSG v1 envelopes for selected models")
    sp.add_argument("session", help="Session name")
    sp.add_argument("--to", nargs="+", required=True, help="Targets, e.g., gpt-5 claude gemini grok")
    sp.add_argument("--subject", help="Subject line", default=None)
    sp.add_argument("--type", help="Message type", default="prompt")
    sp.add_argument("--parents", nargs="*", help="Parent node id prefixes", default=None)
    sp.add_argument("--from-actor", dest="from_actor", help="From actor (default user@cli)", default=None)
    sp.add_argument("--body", help="Body path or '-' for stdin", default="-")
    sp.set_defaults(func=cmd_compose)

    sp = sub.add_parser("ingest-msg", help="Ingest a replied MMSG v1 envelope from stdin or file")
    sp.add_argument("session", help="Session name")
    sp.add_argument("--from", dest="from_path", help="Path or '-' for stdin", default="-")
    sp.set_defaults(func=cmd_ingest_msg)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
