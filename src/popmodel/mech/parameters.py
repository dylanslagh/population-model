"""The mechanism's parameters, and the paperwork that keeps them honest.

Spec section 6.10, the anti-epicycle rule, is the reason this module exists at
all. A model with a fertility parameter, a retention parameter, a persistence
parameter and an assimilation parameter can fit almost anything if all four are
tuned against the same fertility series. So none of them are tuned. They are
read from a committed table, every one carries a statement of where it came
from, and anything without independent support is labelled a scenario knob
rather than quietly treated as an estimate.

Two things this module enforces
-------------------------------
1. **Every parameter states its basis.** A row with no evidence and no
   provenance will not load. There is no default.
2. **Nothing claims to be verified that is not.** Every value in the table is
   currently marked unverified: they are an assistant's recollection of the
   published literature, not values fetched by a script in this repository.
   That is a real limitation, it is recorded on every parameter, and anything
   this model produces inherits it.

The second point is worth being blunt about. The rest of this project holds to
"every value traces to a source, and the script that fetched it lives in the
repo". These do not, yet. They are good-faith recollections with honest ranges,
which is enough to demonstrate the mechanism and not enough to publish a
number. `verified_fraction` reports how far the table has come, and it is
currently zero.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from popmodel import paths

KINDS = ("sourced", "knob")


class ParameterError(RuntimeError):
    """A parameter is missing, malformed, or claims support it does not have."""


@dataclass(frozen=True)
class Parameter:
    """One mechanism parameter and the terms on which it may be believed."""

    name: str
    value: float
    low: float
    high: float
    unit: str
    kind: str
    verified: bool
    evidence: str
    provenance: str
    notes: str

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ParameterError(f"{self.name}: kind must be one of {KINDS}")
        if not (self.low <= self.value <= self.high):
            raise ParameterError(
                f"{self.name}: value {self.value} is outside its range "
                f"[{self.low}, {self.high}]"
            )
        if not self.provenance.strip():
            raise ParameterError(
                f"{self.name}: every parameter must say where it came from, "
                f"including 'nowhere'"
            )
        if self.kind == "sourced" and not self.evidence.strip():
            raise ParameterError(
                f"{self.name}: a parameter claiming to be sourced must name the "
                f"evidence. If there is none, its kind is 'knob'."
            )
        if self.kind == "knob" and self.verified:
            raise ParameterError(
                f"{self.name}: a scenario knob cannot be verified; there is "
                f"nothing to verify it against"
            )

    @property
    def is_knob(self) -> bool:
        return self.kind == "knob"

    def draw(self, rng: np.random.Generator) -> float:
        """One sample from the parameter's stated range.

        Uniform, deliberately. A tighter shape would imply more knowledge about
        the parameter than the range itself represents.
        """
        return float(rng.uniform(self.low, self.high))

    def describe(self) -> str:
        flag = "knob" if self.is_knob else "sourced"
        seal = "verified" if self.verified else "UNVERIFIED"
        return (
            f"{self.name} = {self.value:g} [{self.low:g}, {self.high:g}] "
            f"{self.unit} ({flag}, {seal})"
        )


@dataclass(frozen=True)
class ParameterSet:
    """The whole table, with the caveats it travels under."""

    parameters: dict[str, Parameter]
    source_path: Path

    def __getitem__(self, name: str) -> Parameter:
        try:
            return self.parameters[name]
        except KeyError as exc:
            raise ParameterError(
                f"no parameter named {name!r} in {self.source_path.name}; "
                f"add it to the table rather than hard-coding a value"
            ) from exc

    def value(self, name: str) -> float:
        return self[name].value

    @property
    def knobs(self) -> list[str]:
        return sorted(n for n, p in self.parameters.items() if p.is_knob)

    @property
    def unverified(self) -> list[str]:
        return sorted(n for n, p in self.parameters.items() if not p.verified)

    @property
    def verified_fraction(self) -> float:
        if not self.parameters:
            return 0.0
        verified = sum(1 for p in self.parameters.values() if p.verified)
        return verified / len(self.parameters)

    def caveat(self) -> str:
        """The sentence that must travel with any output built from these."""
        return (
            f"{len(self.knobs)} of {len(self.parameters)} mechanism parameters "
            f"are scenario knobs with no independent support; "
            f"{len(self.unverified)} are unverified, meaning recorded from "
            f"recollection of the literature rather than fetched by a script in "
            f"this repository"
        )

    def provenance(self) -> dict:
        return {
            "source": str(self.source_path.name),
            "count": len(self.parameters),
            "knobs": self.knobs,
            "unverified": self.unverified,
            "verified_fraction": self.verified_fraction,
            "caveat": self.caveat(),
            "parameters": {
                name: {
                    "value": p.value,
                    "range": [p.low, p.high],
                    "kind": p.kind,
                    "verified": p.verified,
                    "evidence": p.evidence,
                    "provenance": p.provenance,
                }
                for name, p in sorted(self.parameters.items())
            },
        }


def table_path() -> Path:
    return paths.REFERENCE / "mechanism_parameters.csv"


def _boolean(text: str, name: str) -> bool:
    value = str(text).strip().upper()
    if value in ("TRUE", "T", "YES", "1"):
        return True
    if value in ("FALSE", "F", "NO", "0", ""):
        return False
    raise ParameterError(f"{name}: verified must be TRUE or FALSE, got {text!r}")


def load(path: Path | None = None) -> ParameterSet:
    """Read the committed parameter table, refusing anything unlabelled."""
    path = path or table_path()
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            expected = {
                "name", "value", "low", "high", "unit", "kind", "verified",
                "evidence", "provenance", "notes",
            }
            missing = expected - set(reader.fieldnames or ())
            if missing:
                raise ParameterError(
                    f"{path.name} is missing column(s): {sorted(missing)}"
                )
            rows = list(reader)
    except FileNotFoundError as exc:
        raise ParameterError(f"the mechanism parameter table is missing: {path}") from exc

    parameters: dict[str, Parameter] = {}
    for row in rows:
        name = str(row["name"]).strip()
        if not name:
            raise ParameterError(f"{path.name} has a row with no parameter name")
        if name in parameters:
            raise ParameterError(f"{path.name} repeats parameter {name!r}")
        try:
            numbers = {k: float(row[k]) for k in ("value", "low", "high")}
        except (TypeError, ValueError) as exc:
            raise ParameterError(f"{name}: value, low and high must be numbers") from exc
        parameters[name] = Parameter(
            name=name,
            unit=str(row["unit"]).strip(),
            kind=str(row["kind"]).strip(),
            verified=_boolean(row["verified"], name),
            evidence=str(row["evidence"]),
            provenance=str(row["provenance"]),
            notes=str(row["notes"]),
            **numbers,
        )

    if not parameters:
        raise ParameterError(f"{path.name} contains no parameters")
    return ParameterSet(parameters=parameters, source_path=path)
