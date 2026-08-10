# Local tools and data locations

This file is the location map for the current Windows workstation. These paths
are machine-specific and mostly point to large, untracked files. They are
written down here so a new session does not have to rediscover where R or the
UW data live.

## Project and runtimes

| Item | Exact path |
|---|---|
| Repository | `C:\Users\dslag\Documents\Codex\2026-08-09\i\population-model` |
| Workspace | `C:\Users\dslag\Documents\Codex\2026-08-09\i` |
| Project Python | `C:\Users\dslag\Documents\Codex\2026-08-09\i\population-model\.venv\Scripts\python.exe` |
| R 4.4.2 | `C:\Users\dslag\Documents\Codex\2026-08-09\i\work\tools\R-4.4.2\bin\Rscript.exe` |
| Rtools44 root | `C:\Users\dslag\Documents\Codex\2026-08-09\i\work\tools\rtools44` |
| Rtools `make` | `C:\Users\dslag\Documents\Codex\2026-08-09\i\work\tools\rtools44\usr\bin\make.exe` |
| Tectonic 0.17.0 | `C:\Users\dslag\Documents\Codex\2026-08-09\i\work\tectonic-0.17.0\tectonic.exe` |
| Pinned R package library | `C:\Users\dslag\Documents\Codex\2026-08-09\i\population-model\r\uw-extract\library\R-4.4.2` |
| R package source cache | `C:\Users\dslag\Documents\Codex\2026-08-09\i\population-model\r\uw-extract\sources` |

R and Rtools are local, portable installations. They are not expected to appear
in the Windows Start menu or on the normal command path. Use the exact paths
above. They remain outside the repository because they are large third-party
runtimes, not project source.

## UW archives and extracted data

| Item | Exact path |
|---|---|
| Annual TFR archive | `C:\Users\dslag\Documents\Codex\2026-08-09\i\population-model\data\raw\UW_WPP2024\TFR1simWPP2024.tgz` |
| Annual e0 archive | `C:\Users\dslag\Documents\Codex\2026-08-09\i\population-model\data\raw\UW_WPP2024\e01simWPP2024.tgz` |
| TFR simulation directory | `C:\Users\dslag\Documents\Codex\2026-08-09\i\population-model\data\interim\UW_WPP2024\native\tfr_annual\TFR1unc\sim20241101` |
| e0 simulation directory | `C:\Users\dslag\Documents\Codex\2026-08-09\i\population-model\data\interim\UW_WPP2024\native\e0_annual\e01\sim20241101` |
| Finland accessor export | `C:\Users\dslag\Documents\Codex\2026-08-09\i\population-model\data\interim\UW_WPP2024\exports\246` |

The Finland export contains `locations.csv`, `metadata.json`,
`r-metadata.tsv`, `session-info.txt`, `shifts.csv`, and `trajectories.csv`.
Raw archives, unpacked R objects, and exports are intentionally ignored by git.
Their checksums and validation receipts live in `data/manifest/` and are
committed.

## Copy-ready PowerShell setup

Run this from the repository root:

```powershell
$repo = 'C:\Users\dslag\Documents\Codex\2026-08-09\i\population-model'
$python = Join-Path $repo '.venv\Scripts\python.exe'
$rscript = 'C:\Users\dslag\Documents\Codex\2026-08-09\i\work\tools\R-4.4.2\bin\Rscript.exe'
$env:RTOOLS44_HOME = 'C:\Users\dslag\Documents\Codex\2026-08-09\i\work\tools\rtools44'
$env:TECTONIC = 'C:\Users\dslag\Documents\Codex\2026-08-09\i\work\tectonic-0.17.0\tectonic.exe'

& $python --version
& $rscript --version
```

To verify or rebuild the pinned R reader:

```powershell
& $rscript --vanilla r\uw-extract\bootstrap.R
& $python scripts\export_uw_fixture.py --rscript $rscript
```

The archives are already present. Before any attempted download, run:

```powershell
& $python scripts\fetch_uw_posteriors.py --check
```

## Paper files

The early scaffold is in:

- LaTeX entry point: `paper/main.tex`
- Section sources: `paper/sections/`
- Bibliography: `paper/bibliography/`
- Stable reviewed PDF: `paper/population-model.pdf`
- Paper landing page: `paper/index.html`

The local PDF builder uses the Tectonic path above. The current scaffold is not
the final research paper and is not the immediate work priority; see
`NEXT_SESSION.md` and `paper/README.md`.

## Website files

- Authoritative generator and HTML template: `scripts/build_map.py`
- Generated committed page: `index.html`
- Map QA: `scripts/check_map.py`
- Exact public-payload staging: `scripts/build_public.py`
- Staging output: `dist/` (ignored by git)

The current authenticated deployment is
<https://hub.dylanslagh.com/population-model/>. There is no genuinely public
production deployment yet.

*All paths above were checked on 2026-08-10.*
