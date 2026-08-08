"""Turn WPP's CSVs into the arrays the engine eats.

The source files are hundreds of megabytes of gzipped text with one row per
country-year-age-sex-variant. The engine wants dense numeric arrays. This
module is the whole of the distance between those two things, and it is
deliberately boring.

Three rules it enforces, all from spec section 14:

* Unmatched or unexpected location codes are a build error, never a silent
  drop (rule 5). If WPP adds a country, this crashes rather than quietly
  projecting 236 of them.
* Units are converted exactly once, here. WPP publishes population in
  thousands and fertility rates per 1000 women. Everything downstream is in
  people and in births per woman.
* Nothing is smoothed, patched or filled. If a value is missing, the ingest
  says so and stops.

Output is a single .npz per bundle plus a JSON sidecar recording which source
files, which checksums, and which revision produced it. That sidecar is what
lets a stored prediction from 2026 still be traced in 2070.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from popmodel import paths
from popmodel.engine import cohort
from popmodel.sources import fetch, wpp2024

# WPP publishes population in thousands and fertility per 1000 women.
THOUSANDS_TO_PEOPLE = 1000.0
PER_1000_TO_PER_WOMAN = 1e-3

BASE_YEAR = 2024  # spec 5.1: fork at 2024, not 2100
LAST_WPP_YEAR = 2100

COUNTRY_TYPE = "Country/Area"
CHUNK = 2_000_000

# WPP 2024 carries this many countries and areas. Hard-coded on purpose: if the
# number changes, something changed in the source and a human should look.
EXPECTED_N_COUNTRIES = 237


class IngestError(RuntimeError):
    """Something about the source data is not what this code was written for."""


@dataclass(frozen=True)
class Bundle:
    """Everything a projection run needs, plus proof of where it came from."""

    iso3: list[str]
    loc_id: np.ndarray  # (L,) UN LocID
    name: list[str]
    years: np.ndarray  # (T,) rate years, 2024..2100
    pop_base: np.ndarray  # (L, 2, 101) people, 1 Jan 2024
    sx: np.ndarray  # (T, L, 2, 101) survival ratios, UN "into age a" sense
    asfr: np.ndarray  # (T, L, 101) births per woman per year, medium variant
    srb: np.ndarray  # (T, L) male births per female birth
    asfr_constant: np.ndarray  # (L, 101) the UN's own constant-fertility rates
    provenance: dict

    @property
    def n_countries(self) -> int:
        return len(self.iso3)

    def index(self, iso3: str) -> int:
        try:
            return self.iso3.index(iso3)
        except ValueError as exc:
            raise KeyError(f"{iso3!r} is not in this bundle") from exc


# --------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------


def _read(key: str, usecols: list[str], where) -> pd.DataFrame:
    """Stream one gzipped WPP CSV, keeping only the rows `where` accepts."""
    path = fetch.raw_path(key)
    keep = []
    reader = pd.read_csv(
        path,
        usecols=usecols,
        chunksize=CHUNK,
        low_memory=False,
        encoding="utf-8-sig",
    )
    for chunk in reader:
        sel = chunk[where(chunk)]
        if len(sel):
            keep.append(sel)
    if not keep:
        raise IngestError(f"{path.name}: no rows survived the filter")
    return pd.concat(keep, ignore_index=True)


def _country_rows(chunk: pd.DataFrame, years: tuple[int, int], variant: str | None = "Medium"):
    mask = (
        (chunk["LocTypeName"] == COUNTRY_TYPE)
        & (chunk["Time"] >= years[0])
        & (chunk["Time"] <= years[1])
    )
    if variant is not None:
        mask &= chunk["Variant"] == variant
    return mask


def country_table() -> pd.DataFrame:
    """The canonical list of countries and areas: LocID, ISO3, name, parent.

    This is the spine everything else is joined onto. Sorted by LocID so the
    array order is stable across rebuilds and across machines.
    """
    df = _read(
        "indicators_medium",
        ["LocID", "ISO3_code", "ISO2_code", "LocTypeName", "ParentID", "Location", "Time", "Variant"],
        lambda c: _country_rows(c, (BASE_YEAR, BASE_YEAR)),
    )
    df = df.drop_duplicates(subset="LocID").sort_values("LocID").reset_index(drop=True)

    missing = df["ISO3_code"].isna() | (df["ISO3_code"].astype(str).str.len() != 3)
    if missing.any():
        bad = df.loc[missing, ["LocID", "Location"]].to_dict("records")
        raise IngestError(
            "Countries with no usable ISO3 code, which the crosswalk cannot key on:\n"
            + "\n".join(f"  LocID {r['LocID']}: {r['Location']}" for r in bad)
        )
    if len(df) != EXPECTED_N_COUNTRIES:
        raise IngestError(
            f"Expected {EXPECTED_N_COUNTRIES} countries and areas in "
            f"{wpp2024.REVISION}, found {len(df)}. The source changed shape; do "
            "not paper over this, work out what moved and update "
            "EXPECTED_N_COUNTRIES with a note."
        )
    return df[["LocID", "ISO3_code", "ISO2_code", "Location", "ParentID"]]


def _dense(
    df: pd.DataFrame,
    countries: pd.DataFrame,
    years: np.ndarray,
    value_cols: list[str],
    age_col: str = "AgeGrpStart",
    n_ages: int = cohort.N_AGES,
    what: str = "values",
) -> np.ndarray:
    """Pivot a long table into (T, L, n_values, n_ages), failing loudly on holes."""
    loc_pos = {int(v): i for i, v in enumerate(countries["LocID"])}
    year_pos = {int(v): i for i, v in enumerate(years)}

    unknown = set(df["LocID"].unique()) - set(loc_pos)
    if unknown:
        raise IngestError(
            f"{what}: {len(unknown)} location code(s) not in the country table: "
            f"{sorted(unknown)[:10]}. Spec rule 5: fail loudly, never drop."
        )

    out = np.full((len(years), len(loc_pos), len(value_cols), n_ages), np.nan, dtype=np.float64)
    li = df["LocID"].map(loc_pos).to_numpy()
    ti = df["Time"].map(year_pos).to_numpy()
    ai = df[age_col].to_numpy(dtype=np.int64)
    if ai.max() >= n_ages or ai.min() < 0:
        raise IngestError(f"{what}: ages outside 0..{n_ages - 1} (saw {ai.min()}..{ai.max()})")
    for vi, col in enumerate(value_cols):
        out[ti, li, vi, ai] = df[col].to_numpy(dtype=np.float64)
    return out


def _require_complete(arr: np.ndarray, what: str, countries: pd.DataFrame, years: np.ndarray) -> None:
    if not np.isnan(arr).any():
        return
    bad = np.argwhere(np.isnan(arr))
    first = bad[0]
    iso = countries["ISO3_code"].iloc[first[1]]
    raise IngestError(
        f"{what}: {len(bad)} missing cell(s). First is {iso} in {years[first[0]]} "
        f"at index {tuple(int(x) for x in first[2:])}. WPP has no gaps (spec 4.5), "
        "so this is a reshaping bug or a changed file, not missing data."
    )


# --------------------------------------------------------------------------
# the pieces
# --------------------------------------------------------------------------


def base_population(countries: pd.DataFrame) -> np.ndarray:
    """(L, 2, 101) people on 1 January 2024."""
    df = _read(
        "pop_jan1_single_proj",
        ["LocID", "LocTypeName", "Time", "Variant", "AgeGrpStart", "PopMale", "PopFemale"],
        lambda c: _country_rows(c, (BASE_YEAR, BASE_YEAR)),
    )
    years = np.array([BASE_YEAR])
    dense = _dense(df, countries, years, ["PopFemale", "PopMale"], what="base population")
    _require_complete(dense, "base population", countries, years)
    return dense[0] * THOUSANDS_TO_PEOPLE


def medium_population(countries: pd.DataFrame, years: np.ndarray) -> np.ndarray:
    """(T, L, 2, 101) the UN's own medium-variant path, 1 January of each year.

    Not an engine input. It is the reference the engine is checked against, and
    the thing net migration by age gets backed out of.
    """
    df = _read(
        "pop_jan1_single_proj",
        ["LocID", "LocTypeName", "Time", "Variant", "AgeGrpStart", "PopMale", "PopFemale"],
        lambda c: _country_rows(c, (int(years[0]), int(years[-1]))),
    )
    dense = _dense(df, countries, years, ["PopFemale", "PopMale"], what="medium population")
    _require_complete(dense, "medium population", countries, years)
    return dense * THOUSANDS_TO_PEOPLE


def survival_ratios(countries: pd.DataFrame, years: np.ndarray) -> np.ndarray:
    """(T, L, 2, 101) the Sx column of the complete life tables.

    Read the survival-ratio note at the top of engine/cohort.py before using
    these: sx[a] is survival INTO age a.
    """
    out = np.full((len(years), len(countries), cohort.N_SEXES, cohort.N_AGES), np.nan)
    for sex_index, key in ((cohort.FEMALE, "life_table_female"), (cohort.MALE, "life_table_male")):
        df = _read(
            key,
            ["LocID", "LocTypeName", "Time", "Variant", "AgeGrpStart", "Sx"],
            lambda c: _country_rows(c, (int(years[0]), int(years[-1]))),
        )
        dense = _dense(df, countries, years, ["Sx"], what=f"life table ({key})")
        _require_complete(dense, f"life table ({key})", countries, years)
        out[:, :, sex_index, :] = dense[:, :, 0, :]

    if (out > 1.0).any() or (out < 0.0).any():
        n = int(((out > 1.0) | (out < 0.0)).sum())
        raise IngestError(f"{n} survival ratio(s) outside [0, 1]; that is not a probability")
    return out


# WPP's single-age fertility file covers these ages and no others.
SINGLE_AGE_FERT_MIN = 15
SINGLE_AGE_FERT_MAX = 49
# The five-year file covers 10-54. These are the bands it adds.
TAIL_BANDS = ((10, 14), (50, 54))


def fertility(countries: pd.DataFrame, years: np.ndarray, variant: str = "Medium") -> np.ndarray:
    """(T, L, 101) births per woman per year, zero outside ages 10-54.

    Assembled from two files, because neither is sufficient alone. The
    single-age file gives ages 15-49 at the resolution the engine works in. The
    five-year file is the only place ages 10-14 and 50-54 appear, and leaving
    them out costs about 0.3% of world births every year - which compounds into
    a visible bias by 2100 and a large one by 2150.

    Within each five-year tail band every single age is given the band's rate.
    That is correct for the birth total (the rate's denominator is the whole
    band), and it does misplace mothers by a year or two inside the band. The
    consequence is second-order and the check below bounds it: the resulting
    total fertility rate is compared against the UN's own published TFR.
    """
    span = (int(years[0]), int(years[-1]))
    single = _read(
        "fertility_age1",
        ["LocID", "LocTypeName", "Time", "Variant", "AgeGrpStart", "ASFR"],
        lambda c: _country_rows(c, span, variant=variant),
    )
    ages = single["AgeGrpStart"]
    if ages.min() != SINGLE_AGE_FERT_MIN or ages.max() != SINGLE_AGE_FERT_MAX:
        raise IngestError(
            f"single-age fertility file covers ages {ages.min()}-{ages.max()}, "
            f"expected {SINGLE_AGE_FERT_MIN}-{SINGLE_AGE_FERT_MAX}"
        )
    dense = _dense(single, countries, years, ["ASFR"], what=f"fertility ({variant})")[:, :, 0, :]
    dense[:, :, :SINGLE_AGE_FERT_MIN] = 0.0
    dense[:, :, SINGLE_AGE_FERT_MAX + 1 :] = 0.0
    _require_complete(dense[..., None], f"fertility ({variant})", countries, years)

    five = _read(
        "fertility_age5",
        ["LocID", "LocTypeName", "Time", "Variant", "AgeGrpStart", "AgeGrpSpan", "ASFR"],
        lambda c: _country_rows(c, span, variant=variant),
    )
    if set(five["AgeGrpSpan"].unique()) != {5}:
        raise IngestError("five-year fertility file has a group that is not five years wide")
    bands = five[five["AgeGrpStart"].isin([lo for lo, _ in TAIL_BANDS])]
    band_dense = _dense(
        bands.assign(BandIdx=bands["AgeGrpStart"].map({lo: i for i, (lo, _) in enumerate(TAIL_BANDS)})),
        countries,
        years,
        ["ASFR"],
        age_col="BandIdx",
        n_ages=len(TAIL_BANDS),
        what=f"tail fertility ({variant})",
    )[:, :, 0, :]
    _require_complete(band_dense[..., None], f"tail fertility ({variant})", countries, years)
    for i, (lo, hi) in enumerate(TAIL_BANDS):
        dense[:, :, lo : hi + 1] = band_dense[:, :, i : i + 1]

    _check_tfr_against_published(dense * PER_1000_TO_PER_WOMAN, countries, years, variant)
    return dense * PER_1000_TO_PER_WOMAN


def _check_tfr_against_published(
    asfr: np.ndarray, countries: pd.DataFrame, years: np.ndarray, variant: str, tol: float = 0.01
) -> None:
    """Assembled rates must add up to the UN's own TFR. Loudly, or not at all.

    This is the check that caught the missing 10-14 and 50-54 bands in the
    first place, so it stays in the build permanently.
    """
    if variant != "Medium":
        return  # published TFR for other variants lives in a different file
    df = _read(
        "indicators_medium",
        ["LocID", "LocTypeName", "Time", "Variant", "TFR"],
        lambda c: _country_rows(c, (int(years[0]), int(years[-1]))),
    ).assign(AgeGrpStart=0)
    published = _dense(df, countries, years, ["TFR"], n_ages=1, what="published TFR")[:, :, 0, 0]
    diff = np.abs(asfr.sum(axis=-1) - published)
    worst = np.unravel_index(int(diff.argmax()), diff.shape)
    if diff[worst] > tol:
        iso = countries["ISO3_code"].iloc[worst[1]]
        raise IngestError(
            f"Assembled fertility does not reproduce the UN's published TFR. "
            f"Worst: {iso} in {years[worst[0]]}, ours "
            f"{asfr.sum(axis=-1)[worst]:.4f} vs published {published[worst]:.4f} "
            f"(tolerance {tol}). Something is missing from the age range or the "
            "variant filter."
        )
    print(f"  fertility check     max TFR error vs published: {diff.max():.5f}")


def sex_ratio_at_birth(countries: pd.DataFrame, years: np.ndarray) -> np.ndarray:
    """(T, L) male births per female birth. WPP publishes it per 100 girls."""
    df = _read(
        "indicators_medium",
        ["LocID", "LocTypeName", "Time", "Variant", "SRB"],
        lambda c: _country_rows(c, (int(years[0]), int(years[-1]))),
    )
    df = df.assign(AgeGrpStart=0)
    dense = _dense(df, countries, years, ["SRB"], n_ages=1, what="sex ratio at birth")
    _require_complete(dense, "sex ratio at birth", countries, years)
    srb = dense[:, :, 0, 0] / 100.0
    if (srb < 0.9).any() or (srb > 1.3).any():
        lo, hi = float(srb.min()), float(srb.max())
        raise IngestError(f"sex ratio at birth outside a believable 0.9-1.3: saw {lo:.3f}-{hi:.3f}")
    return srb


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------


def build_bundle(last_year: int = LAST_WPP_YEAR) -> Bundle:
    years = np.arange(BASE_YEAR, last_year + 1)
    countries = country_table()

    print(f"  countries          {len(countries)}")
    pop_base = base_population(countries)
    print(f"  base population    {pop_base.sum() / 1e9:.4f} billion on 1 Jan {BASE_YEAR}")
    sx = survival_ratios(countries, years)
    print(f"  survival ratios    {sx.shape}")
    asfr = fertility(countries, years)
    print(f"  fertility          {asfr.shape}")
    srb = sex_ratio_at_birth(countries, years)
    print(f"  sex ratio at birth {srb.shape}")

    # The UN's constant-fertility variant does not freeze the 2024 rates; it
    # freezes 2023's, which are about 0.6% higher because fertility is falling.
    # Reading their actual frozen rates rather than assuming ours turns the
    # constant-fertility comparison into a genuine test of the engine over 76
    # years instead of a comparison of two different assumptions.
    asfr_constant = fertility(countries, years[:1], variant="Constant fertility")[0]
    print(f"  constant fertility {asfr_constant.shape} (world mean TFR "
          f"{asfr_constant.sum(axis=-1).mean():.4f} vs medium 2024 "
          f"{asfr[0].sum(axis=-1).mean():.4f})")

    manifest = fetch.load_manifest()
    provenance = {
        "revision": wpp2024.REVISION,
        "revision_label": wpp2024.REVISION_LABEL,
        "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base_year": BASE_YEAR,
        "last_rate_year": int(last_year),
        "units": {
            "population": "people",
            "asfr": "births per woman per year",
            "srb": "male births per female birth",
            "sx": "survival ratio into age a (UN Sx convention)",
        },
        "source_files": {
            k: {"filename": v["filename"], "sha256": v["sha256"]} for k, v in manifest["files"].items()
        },
    }

    return Bundle(
        iso3=countries["ISO3_code"].tolist(),
        loc_id=countries["LocID"].to_numpy(dtype=np.int64),
        name=countries["Location"].tolist(),
        years=years,
        pop_base=pop_base,
        sx=sx,
        asfr=asfr,
        srb=srb,
        asfr_constant=asfr_constant,
        provenance=provenance,
    )


def bundle_path() -> Path:
    return paths.PROCESSED / f"{wpp2024.REVISION.lower()}_bundle.npz"


def save_bundle(bundle: Bundle, path: Path | None = None) -> Path:
    path = path or bundle_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        iso3=np.array(bundle.iso3),
        loc_id=bundle.loc_id,
        name=np.array(bundle.name),
        years=bundle.years,
        pop_base=bundle.pop_base,
        sx=bundle.sx.astype(np.float32),
        asfr=bundle.asfr.astype(np.float32),
        srb=bundle.srb.astype(np.float32),
        asfr_constant=bundle.asfr_constant.astype(np.float32),
    )
    path.with_suffix(".json").write_text(
        json.dumps(bundle.provenance, indent=2) + "\n", encoding="utf-8"
    )
    return path


def load_bundle(path: Path | None = None) -> Bundle:
    path = path or bundle_path()
    if not path.exists():
        raise FileNotFoundError(
            f"{path.name} has not been built.\n  Run:  python scripts/build_bundle.py"
        )
    z = np.load(path, allow_pickle=False)
    provenance = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    return Bundle(
        iso3=[str(s) for s in z["iso3"]],
        loc_id=z["loc_id"],
        name=[str(s) for s in z["name"]],
        years=z["years"],
        pop_base=z["pop_base"].astype(np.float64),
        sx=z["sx"].astype(np.float64),
        asfr=z["asfr"].astype(np.float64),
        srb=z["srb"].astype(np.float64),
        asfr_constant=z["asfr_constant"].astype(np.float64),
        provenance=provenance,
    )
