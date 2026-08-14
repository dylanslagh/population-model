# Local tools and data locations

This file is the location map for the current Windows workstation. Everything
here is either machine-specific or large and untracked, written down so a new
session does not have to rediscover where R or the UW data live.

**The repository is `C:\Users\dslag\Documents\GitHub\population-model`, and it
is the only copy.** A second working copy under `Documents\Codex\` was deleted
on 2026-08-10 once its data had been brought here. If one reappears, it is a
scratch copy: do not work in it.

## Runtimes

R, Rtools and Tectonic are large third-party runtimes, so they stay outside the
repository. They are portable installations and will not appear in the Start
menu or on the normal command path. Every script that needs R takes its path as
`--rscript`, so nothing depends on R being installed anywhere in particular.

| Item | Exact path |
|---|---|
| Python 3.14 | on `PATH` as `python`; bare runtime has no project packages |
| Project Python 3.11 | `.venv\Scripts\python.exe`; created 2026-08-13 with system scientific packages plus pytest |
| R 4.4.2 | `C:\Users\dslag\Documents\Codex\2026-08-09\i\work\tools\R-4.4.2\bin\Rscript.exe` |
| Rtools44 root | `C:\Users\dslag\Documents\Codex\2026-08-09\i\work\tools\rtools44` |
| Tectonic 0.17.0 | `C:\Users\dslag\Documents\Codex\2026-08-09\i\work\tectonic-0.17.0\tectonic.exe` |
| Pinned R packages | `r\uw-extract\library\R-4.4.2` (inside the repository) |
| R package sources | `r\uw-extract\sources` (inside the repository) |

## UW data

All inside the repository, all gitignored. Their checksums and validation
receipts are committed in `data\manifest\`.

| Item | Path | Size |
|---|---|---|
| Annual TFR archive | `data\raw\UW_WPP2024\TFR1simWPP2024.tgz` | 1.8 GB |
| Annual e0 archive | `data\raw\UW_WPP2024\e01simWPP2024.tgz` | 435 MB |
| Migration archive | `data\raw\UW_WPP2024\mig1trajWPP2024.tgz` | 94 MB |
| TFR simulation | `data\interim\UW_WPP2024\native\tfr_annual\TFR1unc\sim20241101` | |
| e0 simulation | `data\interim\UW_WPP2024\native\e0_annual\e01\sim20241101` | |
| Migration CSV | `data\interim\UW_WPP2024\migration\ascii_trajectories.csv` | 480 MB |
| Country exports | `data\interim\UW_WPP2024\exports\<LocID>\` | 1.5 GB, 236 dirs |
| Compacted draws | `data\processed\uw_wpp2024_draws.npz` | 421 MB |
| Compacted migration | `data\processed\uw_wpp2024_migration.npz` | |

Each country export contains `locations.csv`, `metadata.json`, `r-metadata.tsv`,
`session-info.txt`, `shifts.csv` and `trajectories.csv`. The committed receipts
are `uw_wpp2024_files.json`, `uw_wpp2024_full_export.json`,
`uw_wpp2024_finland_fixture.json` and `uw_wpp2024_migration.json`.

The archives are already downloaded. Before any attempted re-download:

```powershell
python scripts\fetch_uw_posteriors.py --check
```

## Copy-ready PowerShell setup

From the repository root:

```powershell
$python = '.\.venv\Scripts\python.exe'
$rscript = 'C:\Users\dslag\Documents\Codex\2026-08-09\i\work\tools\R-4.4.2\bin\Rscript.exe'
$env:RTOOLS44_HOME = 'C:\Users\dslag\Documents\Codex\2026-08-09\i\work\tools\rtools44'
$env:TECTONIC = 'C:\Users\dslag\Documents\Codex\2026-08-09\i\work\tectonic-0.17.0\tectonic.exe'
& $python --version
& $rscript --version
```

Use `& $python -m pytest tests -q` for the test suite. The bare Python 3.14 on
`PATH` does not currently have NumPy, pandas, or pytest.

To verify or rebuild the pinned R reader:

```powershell
& $rscript --vanilla r\uw-extract\bootstrap.R
python scripts\export_uw_fixture.py --check-only
```

## Paper files

The scaffold is `paper\main.tex` with sections in `paper\sections\`,
bibliography in `paper\bibliography\`, the built PDF at
`paper\population-model.pdf` and a landing page at `paper\index.html`. It was
written before there were results worth writing up and is not the intended
research paper; see `NEXT_SESSION.md`.

## Website files

- Generator and HTML template: `scripts\build_map.py`
- Generated committed page: `index.html` at the repository root
- Map QA, including the uncertainty-band checks: `scripts\check_map.py`
- Public-payload staging: `scripts\build_public.py`, output into `dist\` (ignored)

The live route is <https://hub.dylanslagh.com/population-model/>, password-gated.
Pushing this repository does not rebuild the hub:

```bash
gh workflow run publish.yml --repo dylanslagh/project-hub
```

*All paths checked on 2026-08-10.*
