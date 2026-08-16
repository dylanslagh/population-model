"""Render the conversations that produced this project into readable Markdown.

The paper lists two language models as authors, which is only defensible if a
reader can see what they actually did. Neither tool offers an export that is fit
for that purpose: Claude Code has no share feature at all and keeps sessions as
local JSONL, and while ChatGPT share links exist they render client-side, so
nothing automated -- including a web archiver -- can read one. Relying on them
would mean the record disappears the day either company changes a URL scheme.

So the record is generated here and committed, and the share links become
convenience pointers rather than the archive.

What is kept and what is dropped
--------------------------------
Kept: every visible message from the user and from the model, in order, and a
one-line summary of each tool call so the shape of the work is visible.

Dropped, with counts reported in the index so the omission is not silent:

* **Tool output.** The transcripts contain the full text of every file read.
  Including it would multiply the size by roughly twenty and would republish
  data this project deliberately does not redistribute -- the cohort fertility
  tabulations are used under terms that forbid it, and leaking them through a
  transcript instead of a data file would be no better.
* **Model reasoning.** Claude Code stores thinking blocks in plain text and
  Codex stores them encrypted, so including them would produce a record that is
  detailed for one author and blank for the other. They stay in the raw files.
* **Subagent traffic and injected context.** System reminders, plugin lists and
  file-attachment preambles are not conversation.

Redaction
---------
Absolute paths are rewritten to `~`, and the export refuses to write anything if
a credential-shaped string appears. That check has never fired; it is here so
that if it ever does, the failure is loud rather than a quiet publication.

    python scripts/export_conversations.py
    python scripts/export_conversations.py --check   # scan without writing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "conversations"
HOME = Path.home()

CLAUDE_SESSIONS = HOME / ".claude/projects/C--Users-dslag-Documents-GitHub-population-model"
CODEX_SESSIONS = HOME / ".codex/sessions"

#: Credential shapes. A hit stops the export rather than being masked, because a
#: masked secret is still a secret that was once in a file this script wrote.
SECRET_PATTERNS = [
    re.compile(p) for p in (
        r"ghp_[A-Za-z0-9]{20,}", r"gho_[A-Za-z0-9]{20,}",
        r"github_pat_[A-Za-z0-9_]{20,}",
        r"sk-[A-Za-z0-9]{20,}", r"sk-ant-[A-Za-z0-9_-]{20,}",
        r"AKIA[0-9A-Z]{16}", r"xox[baprs]-[A-Za-z0-9-]{10,}",
    )
]

#: Text the harness injects into the user turn. Not conversation.
INJECTED_PREFIXES = (
    "<system-reminder>", "<recommended_plugins>", "<app-context>",
    "<user-prompt-submit-hook>", "[Request interrupted",
    "# Files mentioned by the user:", "Caveat: The messages below",
    "<command-name>", "<local-command-stdout>", "<command-message>",
    "<task-notification>", "[SYSTEM NOTIFICATION",
)


@dataclass
class Turn:
    role: str          # "user", "assistant", or "tool"
    text: str
    timestamp: str = ""


@dataclass
class Conversation:
    key: str
    title: str
    tool: str
    source: Path
    turns: list[Turn] = field(default_factory=list)
    dropped: dict[str, int] = field(default_factory=dict)
    share_url: str = ""
    file_started: str = ""
    file_ended: str = ""

    @property
    def started(self) -> str:
        return self.file_started[:10] or "unknown"

    @property
    def ended(self) -> str:
        return self.file_ended[:10] or "unknown"

    def count(self, role: str) -> int:
        return sum(1 for t in self.turns if t.role == role)

    def digest(self) -> str:
        return hashlib.sha256(self.source.read_bytes()).hexdigest()


#: The harness also encodes the home directory into scratch-path names, where it
#: survives a plain prefix replacement: `C--Users-dslag-Documents-...`. Redacting
#: one form and not the other is worse than redacting neither, because it reads
#: as though the remaining one was deliberate.
USER = HOME.name
ENCODED_HOME = re.compile(rf"C--Users-{re.escape(USER)}-[A-Za-z0-9-]*")


def clean(text: str) -> str:
    """Normalise absolute paths, so the record is about the work not the machine."""
    if not text:
        return ""
    # Windows, forward-slash, escaped, and the Git Bash mount form, which is
    # what the shell tool actually emitted for most of this project.
    drive, rest = str(HOME)[0], str(HOME)[2:].replace("\\", "/")
    for form in (str(HOME), str(HOME).replace("\\", "/"),
                 str(HOME).replace("\\", "\\\\"),
                 f"/{drive.lower()}{rest}", f"/{drive.upper()}{rest}"):
        text = text.replace(form, "~")
    text = ENCODED_HOME.sub("<project-scratch>", text)
    return text.strip()


def is_injected(text: str) -> bool:
    stripped = text.lstrip()
    return any(stripped.startswith(prefix) for prefix in INJECTED_PREFIXES)


def summarise_tool(name: str, payload) -> str:
    """One line per tool call: enough to see the shape, not the contents."""
    if isinstance(payload, dict):
        for key in ("file_path", "path", "pattern", "command", "url",
                    "prompt", "description", "query", "skill"):
            if key in payload and isinstance(payload[key], str):
                detail = " ".join(payload[key].split())
                if len(detail) > 110:
                    detail = detail[:107] + "..."
                return f"{name} — {detail}"
        return name
    if isinstance(payload, str):
        detail = " ".join(payload.split())
        return f"{name} — {detail[:107] + '...' if len(detail) > 110 else detail}"
    return name


# ---------------------------------------------------------------- Claude Code

def read_claude(path: Path, title: str, share_url: str = "") -> Conversation:
    convo = Conversation(path.stem[:8], title, "Claude Code", path, share_url=share_url)
    dropped = {"tool output": 0, "reasoning": 0, "subagent": 0, "injected": 0}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        stamp_any = entry.get("timestamp", "")
        if stamp_any:
            convo.file_started = convo.file_started or stamp_any
            convo.file_ended = stamp_any
        kind = entry.get("type")
        if kind not in ("user", "assistant"):
            continue
        if entry.get("isSidechain"):
            dropped["subagent"] += 1
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        stamp = entry.get("timestamp", "")
        content = message.get("content")

        if kind == "user":
            if isinstance(content, str):
                if is_injected(content):
                    dropped["injected"] += 1
                    continue
                convo.turns.append(Turn("user", clean(content), stamp))
            else:
                dropped["tool output"] += 1
            continue

        for block in content if isinstance(content, list) else []:
            block_type = block.get("type")
            if block_type == "text":
                text = clean(block.get("text", ""))
                if text:
                    convo.turns.append(Turn("assistant", text, stamp))
            elif block_type == "thinking":
                dropped["reasoning"] += 1
            elif block_type == "tool_use":
                convo.turns.append(Turn(
                    "tool",
                    clean(summarise_tool(block.get("name", "tool"), block.get("input"))),
                    stamp,
                ))
    convo.dropped = dropped
    return convo


# ------------------------------------------------------ plain-text transcripts

#: The two conversations that designed the project happened in chat rather than
#: in a coding tool, and each app wrote its own transcript. Those files are
#: small, already curated, and shareable, so unlike the JSONL sessions they are
#: committed alongside the render and the render is parsed back out of them.
TEXT_SPEAKERS = (
    (re.compile(r"^\[\d+\]\s+(DYLAN|CLAUDE)\s*$"), {"DYLAN": "user", "CLAUDE": "assistant"}),
    (re.compile(r"^(USER|ASSISTANT):\s*$"), {"USER": "user", "ASSISTANT": "assistant"}),
)


def read_text(path: Path, title: str, share_url: str = "",
              started: str = "") -> Conversation:
    convo = Conversation(path.stem[:8], title, "chat", path, share_url=share_url)
    convo.file_started = convo.file_ended = started
    convo.dropped = {"tool output": 0, "reasoning": 0, "subagent": 0, "injected": 0}

    role, buffer = None, []

    def flush() -> None:
        if role and buffer:
            text = clean("\n".join(buffer))
            # The apps mark elided passages with square brackets on their own
            # line; they are the app's summary, not a message, but dropping them
            # would hide that something was elided.
            if text:
                convo.turns.append(Turn(role, text, started))
        buffer.clear()

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if set(line.strip()) in ({"="}, {"-"}) and len(line.strip()) > 20:
            continue
        matched = None
        for pattern, mapping in TEXT_SPEAKERS:
            hit = pattern.match(line.strip())
            if hit:
                matched = mapping[hit.group(1)]
                break
        if matched:
            flush()
            role = matched
            continue
        if role:
            buffer.append(line)
    flush()
    if not convo.turns:
        raise SystemExit(f"no messages parsed from {path.name}; check its format")
    return convo


# ---------------------------------------------------------------------- Codex

def read_codex(path: Path, title: str, share_url: str = "") -> Conversation:
    convo = Conversation(path.stem.split("-")[-1][:8], title, "Codex", path,
                         share_url=share_url)
    dropped = {"tool output": 0, "reasoning": 0, "subagent": 0, "injected": 0}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        stamp_any = entry.get("timestamp", "")
        if stamp_any:
            convo.file_started = convo.file_started or stamp_any
            convo.file_ended = stamp_any
        if entry.get("type") != "response_item":
            continue
        payload = entry.get("payload", {})
        kind = payload.get("type")
        stamp = entry.get("timestamp", "")

        if kind == "reasoning":
            dropped["reasoning"] += 1
        elif kind == "custom_tool_call_output":
            dropped["tool output"] += 1
        elif kind == "custom_tool_call":
            convo.turns.append(Turn(
                "tool",
                clean(summarise_tool(payload.get("name", "tool"), payload.get("input"))),
                stamp,
            ))
        elif kind == "message":
            role = payload.get("role")
            if role == "developer":
                dropped["injected"] += 1
                continue
            text = clean("\n".join(
                block.get("text", "")
                for block in payload.get("content", [])
                if block.get("type") in ("input_text", "output_text")
            ))
            if not text:
                continue
            if role == "user" and is_injected(text):
                dropped["injected"] += 1
                continue
            convo.turns.append(Turn(
                "user" if role == "user" else "assistant", text, stamp
            ))
    convo.dropped = dropped
    return convo


# --------------------------------------------------------------------- output

def render(convo: Conversation, index: int) -> str:
    lines = [
        f"# {index:02d}. {convo.title}",
        "",
        f"**{convo.tool}** &middot; {convo.started} to {convo.ended} &middot; "
        f"{convo.count('user')} messages from Dylan, "
        f"{convo.count('assistant')} from the model, "
        f"{convo.count('tool')} tool calls.",
        "",
    ]
    if convo.share_url:
        lines += [f"Shared link: <{convo.share_url}>", ""]
    lines += [
        "> Tool output and model reasoning are omitted; see "
        "[README](README.md) for what that leaves out and why.",
        "", "---", "",
    ]
    pending_tools: list[str] = []

    def flush() -> None:
        if not pending_tools:
            return
        lines.append("<details><summary>"
                     f"{len(pending_tools)} tool calls</summary>\n")
        lines.extend(f"- `{call}`" for call in pending_tools)
        lines.append("\n</details>\n")
        pending_tools.clear()

    for turn in convo.turns:
        if turn.role == "tool":
            pending_tools.append(turn.text)
            continue
        flush()
        speaker = "Dylan" if turn.role == "user" else "Model"
        lines.append(f"### {speaker}")
        lines.append("")
        lines.append(turn.text)
        lines.append("")
    flush()
    return "\n".join(lines) + "\n"


def render_index(conversations: list[Conversation], missing: list[dict]) -> str:
    lines = [
        "# Conversation index",
        "",
        "Every conversation that produced this project, in order. Each entry "
        "records the source file it was rendered from and that file's SHA-256, "
        "so a reader can tell whether they are looking at the same material the "
        "export was made from.",
        "",
        "| # | Conversation | Tool | Dates | Dylan | Model | Tools |",
        "|---|---|---|---|--:|--:|--:|",
    ]
    for index, convo in enumerate(conversations, start=1):
        name = f"[{convo.title}]({index:02d}-{slug(convo.title)}.md)"
        lines.append(
            f"| {index:02d} | {name} | {convo.tool} | {convo.started} to "
            f"{convo.ended} | {convo.count('user')} | "
            f"{convo.count('assistant')} | {convo.count('tool')} |"
        )
    for entry in missing:
        lines.append(
            f"| — | {entry['title']} *(not yet exported)* | {entry['tool']} | "
            f"{entry['dates']} | — | — | — |"
        )
    lines += ["", "## What was dropped from each export", "",
              "| Conversation | Tool output | Reasoning | Subagent | Injected |",
              "|---|--:|--:|--:|--:|"]
    for convo in conversations:
        d = convo.dropped
        lines.append(
            f"| {convo.title} | {d['tool output']} | {d['reasoning']} | "
            f"{d['subagent']} | {d['injected']} |"
        )
    lines += ["", "## Source files", "",
              "| Conversation | Source | SHA-256 |", "|---|---|---|"]
    for convo in conversations:
        lines.append(
            f"| {convo.title} | `{convo.source.name}` | `{convo.digest()[:16]}…` |"
        )
    if missing:
        lines += [
            "", "## Known gaps", "",
            "Recorded rather than left silent:", "",
        ]
        lines += [f"- **{e['title']}** ({e['tool']}, {e['dates']}) — {e['why']}"
                  for e in missing]
    lines += ["", f"*Generated by `scripts/export_conversations.py` on "
                  f"{datetime.now():%Y-%m-%d}.*", ""]
    return "\n".join(lines)


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def scan_for_secrets(text: str, where: str) -> None:
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            raise SystemExit(
                f"a credential-shaped string appears in {where}. Nothing has "
                f"been written. Find it, rotate it, and decide deliberately "
                f"what to do before exporting again."
            )


# The conversations, in the order they happened. Titles are Dylan's and the
# tools' own, not invented here.
SOURCES = [
    ("text", "sources/00-claude-design-conversation.txt",
     "Designing the project", "2026-08-08T00:00"),
    ("text", "sources/01-chatgpt-bayesian-hierarchical-model.txt",
     "A hierarchical model, and the case for development pressure",
     "2026-08-08T12:00"),
    ("codex", "2026/08/09/rollout-2026-08-09T15-00-56-019fe7e6-46af-7b02-96de-3d39dcb00b44.jsonl",
     "Population-model handoff and map colours", ""),
    ("claude", "e9fffde5-ee84-4f45-a521-998acaa5dd8e.jsonl",
     "Building the engine, backtest and map", ""),
    ("claude", "ee3deccd-97b5-4043-9011-99268da9e308.jsonl",
     "The probabilistic baseline and the mechanism layer", ""),
    ("codex", "2026/08/13/rollout-2026-08-13T20-02-09-019ffd93-7be4-7270-a6c4-0ac41f19480b.jsonl",
     "Researching the mechanism parameters", ""),
    ("codex", "2026/08/15/rollout-2026-08-15T06-11-38-01a004e7-d884-70a2-a3e1-d1c000b02528.jsonl",
     "Finding the next task", ""),
    ("claude", "1ff8c8ce-f77a-4aed-83f6-e86b1157bbc2.jsonl",
     "The bar-chart race video", ""),
    ("claude", "fd025039-0589-460c-b029-1c146653edfe.jsonl",
     "Writing the paper", ""),
    ("codex", "2026/08/16/rollout-2026-08-16T06-27-51-01a00a1d-0e30-71f3-aaa5-6af05d0426a3.jsonl",
     "Reviewing the paper", ""),
    ("claude", "f7ec965b-b541-4139-bfcb-3b4029d57cce.jsonl",
     "Revising the paper and continuing the rates", ""),
]

#: Conversations known to exist but not exported. Empty is the goal; when it is
#: not, the gap belongs in the index rather than in nobody's memory.
MISSING: list[dict] = []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="scan and report without writing anything")
    args = parser.parse_args()

    conversations: list[Conversation] = []
    for kind, relative, title, share in SOURCES:
        root = {"claude": CLAUDE_SESSIONS, "codex": CODEX_SESSIONS,
                "text": OUT}[kind]
        path = root / relative
        if not path.exists():
            raise SystemExit(f"missing source transcript: {path}")
        if kind == "text":
            conversations.append(read_text(path, title, started=share))
        else:
            reader = read_claude if kind == "claude" else read_codex
            conversations.append(reader(path, title, share))
    # Sort by date, breaking ties in declared order. The two chat transcripts
    # carry a date and no per-message times, so they cannot be ordered against a
    # coding session that began the same day by timestamp alone; the declared
    # order is the sequence the work actually happened in. The tiebreak has to
    # be captured before sorting, because `list.index` during a sort searches a
    # list that is already being reordered underneath it.
    declared = {id(convo): position for position, convo in enumerate(conversations)}
    conversations.sort(key=lambda c: (c.file_started[:10], declared[id(c)]))

    rendered = [render(convo, i)
                for i, convo in enumerate(conversations, start=1)]
    for convo, text in zip(conversations, rendered):
        scan_for_secrets(text, convo.title)

    total_words = sum(len(text.split()) for text in rendered)
    print(f"{len(conversations)} conversations, ~{total_words:,} words")
    for convo in conversations:
        print(f"  {convo.title:52.52s} {convo.tool:12s} "
              f"{convo.count('user'):4d} user  {convo.count('assistant'):4d} model  "
              f"{convo.count('tool'):5d} tools")
    if args.check:
        print("\n--check: nothing written")
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    for index, (convo, text) in enumerate(zip(conversations, rendered), start=1):
        target = OUT / f"{index:02d}-{slug(convo.title)}.md"
        target.write_text(text, encoding="utf-8")
    (OUT / "index.md").write_text(
        render_index(conversations, MISSING), encoding="utf-8"
    )
    written = sum(p.stat().st_size for p in OUT.glob("*.md"))
    print(f"\nwrote {len(conversations) + 1} files to conversations/ "
          f"({written / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
