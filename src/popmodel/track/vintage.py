"""Stored predictions, written once and never edited.

Spec section 9 says this is the contribution and the model is replaceable. The
argument: the 2150 number is unfalsifiable within a lifetime, so the thing
worth building is a scored track record with the methodology attached, so that
somebody in 2070 can ask which prior structure over fertility was well
calibrated and get an answer.

That only works if the files survive contact with fifty years of good
intentions. So:

* A vintage directory is written once. Writing over one raises. Spec rule 2.
* Every file gets a SHA-256, and the vintage records the hash of the model code
  that produced it and the hash of the source data it was built from. A stored
  prediction whose provenance cannot be reconstructed is an anecdote.
* Everything is JSON. No pickles, no parquet, no database. In 2070 the
  dependency that cannot be installed is the one that loses the archive, and
  JSON will still open.
* Each predicted quantity carries its own resolution date and its own source of
  truth, named in advance. Deciding after the fact what a prediction meant is
  the failure mode this whole apparatus exists to prevent.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from popmodel import paths

SCHEMA_VERSION = "1.0"


class VintageExists(RuntimeError):
    """Refusing to overwrite a stored prediction. Spec section 14, rule 2."""


@dataclass
class Quantity:
    """One predicted thing, with the terms of its own grading written down.

    `is_project_claim` matters more than it looks. Early vintages contain
    numbers that are reproductions of somebody else's model, recorded to
    exercise the format and to establish a baseline. Scoring those as if they
    were this project's predictions would flatter or damn it for work it did
    not do.
    """

    id: str
    description: str
    unit: str
    resolution_date: str  # ISO date, or a year, when the truth becomes knowable
    source_of_truth: str  # named in advance: which dataset settles it
    is_project_claim: bool
    kind: str  # "point" | "quantiles" | "samples"
    point: float | None = None
    quantiles: dict[str, float] | None = None
    samples: list[float] | None = None
    scenario: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if self.kind not in ("point", "quantiles", "samples"):
            raise ValueError(f"unknown kind {self.kind!r}")
        have = {
            "point": self.point is not None,
            "quantiles": bool(self.quantiles),
            "samples": bool(self.samples),
        }
        if not have[self.kind]:
            raise ValueError(f"kind is {self.kind!r} but no {self.kind} was given")
        if self.kind == "point" and not self.notes:
            raise ValueError(
                f"{self.id}: a point prediction has no distribution and cannot be "
                "scored with a proper rule. Say in `notes` why it is a point."
            )
        if not self.resolution_date:
            raise ValueError(f"{self.id}: every quantity needs a resolution date")
        if not self.source_of_truth:
            raise ValueError(
                f"{self.id}: name the dataset that will settle this, before the "
                "fact. Spec section 9."
            )


@dataclass
class Vintage:
    """A dated set of predictions plus everything needed to reconstruct it."""

    vintage_id: str
    title: str
    created_utc: str
    schema_version: str
    model: dict
    data: dict
    quantities: list[Quantity] = field(default_factory=list)
    notes: str = ""

    def to_json(self) -> str:
        d = asdict(self)
        d["quantities"] = [
            {k: v for k, v in q.items() if v is not None and v != ""} for q in d["quantities"]
        ]
        return json.dumps(d, indent=2, sort_keys=True) + "\n"


def new_vintage(
    slug: str,
    title: str,
    *,
    model_name: str,
    model_phase: int,
    data_provenance: dict,
    code_paths: list[Path] | None = None,
    notes: str = "",
) -> Vintage:
    """Start a vintage. Its id encodes the date, which is half the point."""
    vid = f"{date.today().isoformat()}-{slug}"
    code_paths = code_paths or _default_code_paths()
    return Vintage(
        vintage_id=vid,
        title=title,
        created_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        schema_version=SCHEMA_VERSION,
        model={
            "name": model_name,
            "build_phase": model_phase,
            "git_commit": _git_commit(),
            # Naming the uncommitted files matters more than a yes/no. A dirty
            # tree only threatens reconstructability if the dirty files are
            # model code, and code_sha256 below settles that either way.
            "git_uncommitted_files": _git_dirty_files(),
            "code_sha256": {
                str(p.relative_to(paths.REPO_ROOT)): _sha256(p) for p in code_paths if p.exists()
            },
        },
        data=data_provenance,
        notes=notes,
    )


def write(vintage: Vintage, *, root: Path | None = None) -> Path:
    """Write a vintage to disk. Refuses if that vintage id already exists."""
    root = root or paths.VINTAGES
    d = root / vintage.vintage_id
    if d.exists():
        raise VintageExists(
            f"{d} already exists. Stored predictions are never overwritten "
            "(spec section 14, rule 2). If today's run differs, that is itself "
            "the interesting fact: give it a new id, or work out why the same "
            "inputs produced a different answer."
        )
    if not vintage.quantities:
        raise ValueError("a vintage with no quantities predicts nothing")

    d.mkdir(parents=True)
    body = vintage.to_json()
    (d / "prediction.json").write_text(body, encoding="utf-8")
    (d / "prediction.sha256").write_text(
        hashlib.sha256(body.encode("utf-8")).hexdigest() + "  prediction.json\n", encoding="utf-8"
    )
    return d


def load(vintage_id: str, *, root: Path | None = None) -> dict:
    root = root or paths.VINTAGES
    p = root / vintage_id / "prediction.json"
    if not p.exists():
        raise FileNotFoundError(f"no vintage {vintage_id!r} in {root}")
    return json.loads(p.read_text(encoding="utf-8"))


def verify_all(*, root: Path | None = None) -> list[tuple[str, bool]]:
    """Recompute every stored vintage's hash. Silent corruption is the enemy."""
    root = root or paths.VINTAGES
    out = []
    for d in sorted(p for p in root.glob("*") if p.is_dir()):
        body = (d / "prediction.json").read_text(encoding="utf-8")
        recorded = (d / "prediction.sha256").read_text(encoding="utf-8").split()[0]
        out.append((d.name, hashlib.sha256(body.encode("utf-8")).hexdigest() == recorded))
    return out


def list_vintages(*, root: Path | None = None) -> list[str]:
    root = root or paths.VINTAGES
    return sorted(p.name for p in root.glob("*") if p.is_dir())


def _default_code_paths() -> list[Path]:
    src = paths.REPO_ROOT / "src" / "popmodel"
    return sorted(src.rglob("*.py"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit() -> str:
    return _git("rev-parse", "HEAD") or "unknown"


def _git_dirty_files() -> list[str]:
    status = _git("status", "--porcelain")
    return [line[3:] for line in status.splitlines() if line.strip()]


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=paths.REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
