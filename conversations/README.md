# The conversations that produced this project

The paper lists two language models as authors. That is only defensible if you
can see what they actually did, so this directory holds the record.

Start with **[index.md](index.md)**, which lists every conversation in order with
its dates, its message counts, the file it was rendered from and that file's
SHA-256.

## Why these are files rather than links

Neither tool offers an export fit for the purpose.

**Claude Code has no share feature.** Sessions are JSONL files on the machine
that ran them. Most of the modelling happened there, so a supplement built out of
share links would be missing the majority of the work.

**Shared links render client-side.** They look fine in a browser and are opaque
to everything else. Checked on 16 August 2026, an automated fetch of the ChatGPT
share link below returned its title and no conversation, and the Claude one
returned an empty page. Web archivers see the same thing, so a shared link is not
a durable citation — it is a pointer that works until someone changes a URL
scheme.

So the record is generated from the local transcripts by
[`scripts/export_conversations.py`](../scripts/export_conversations.py) and
committed here. Where a shared link exists it is recorded as a convenience, not
as the archive.

## What these files contain, and what they leave out

**Kept:** every visible message, from Dylan and from the model, in order; and a
one-line summary of every tool call, collapsed into an expandable block, so the
shape of the work is visible without drowning the conversation.

**Dropped**, with per-conversation counts in [index.md](index.md) so no omission
is silent:

- **Tool output.** The raw transcripts contain the full text of every file read,
  every command run and every search result. Including it would multiply the size
  by roughly twenty, and it would republish material this project deliberately
  does not redistribute: the cohort fertility tabulations behind the dispersion
  parameter are used under terms that forbid it, and leaking them through a
  transcript rather than a data file would be no better.
- **Model reasoning.** Claude Code records thinking in plain text; Codex encrypts
  it. Including it would produce a record that is detailed for one model and
  blank for the other, which would misrepresent both.
- **Subagent traffic and injected context.** System reminders, plugin
  advertisements, file-attachment preambles and the harness's own scaffolding
  are not conversation.

**Redaction.** Absolute paths are rewritten to `~`. The exporter refuses to write
anything at all if a credential-shaped string appears anywhere in the output; it
has never fired. The two chat transcripts contain no tool calls and are rendered
whole.

## What this record shows, which is the point of it

It is not a clean document and it should not be read as one. It contains wrong
turns, numbers that were later corrected, and assumptions that survived longer
than they deserved to. Some of the mistakes are recorded in the paper and its
supplement because they were instructive:

- an absurdity check that itself encoded a stale figure and was wrong for years;
- a rail on the life-expectancy sex gap that clipped a tenth of all values
  because it was written down rather than derived from the data;
- a claim, repeated across several files, that two curves coincided exactly when
  they differ by 0.22%;
- a field named `median_peak` that held a mean.

Each of those was found by a check, and the checks are in the repository. A
reader who wants to know how much to trust the paper is entitled to see how many
times it was wrong first.

## The two design conversations

The first two entries are different in kind from the rest. They happened in chat
rather than in a coding tool, they contain no tool calls, and between them they
produced the specification everything afterwards was built against. Each app
wrote its own transcript, and because those files are small and already curated
they are committed verbatim under [`sources/`](sources/) alongside the render —
unlike the JSONL sessions, which are not.

They are also the most interesting reading here, because the project's ideas and
at least one of its durable mistakes are both visible arriving. The claim that a
constant-fertility projection should reach roughly 244 billion by 2150 — which
the paper's supplement records as an absurdity check that was itself wrong — is
in conversation 01, offered in passing as a sanity test. It became a stated
requirement in the specification and stayed one until the engine was built and
disagreed with it.

## Known gaps

Codex keeps helper-agent logs alongside the main transcripts. They are
delegated tool work rather than conversation, and are not included.

The final conversation is exported while it is still running, so it stops
wherever the export was made rather than where the conversation did. Re-running
the exporter brings it up to date.

Conversations 07 and 09 open with the same message from Dylan. That is not a
duplication error: 09 resumed the same named session after a restart, and the
harness replays the opening prompt. Everything after that first message differs.

**Redaction is best-effort, not a guarantee.** Absolute paths are rewritten in
the four forms this project's tools actually emitted, and a credential scan runs
before anything is written. Two truncated paths survive because the tool-call
summariser cut them off mid-string. The hub review site's address appears in
several conversations; it is password-gated and is already named in the
repository's committed handoff files, so it is left as written rather than
redacted, which would be theatre.

## Regenerating

```powershell
.\.venv\Scripts\python.exe scripts\export_conversations.py --check   # scan only
.\.venv\Scripts\python.exe scripts\export_conversations.py
```

The source transcripts live outside the repository, under `~/.claude/projects/`
and `~/.codex/sessions/`. They are not committed: they are large, they contain
the tool output described above, and they are an implementation detail of two
applications rather than a stable format. The SHA-256 of each is recorded in
[index.md](index.md) so an export can be checked against the file it came from.

More detail can be produced on request — the full reasoning, the tool output, or
the raw transcripts themselves. Ask.
