# UW native-object reader

This is a deliberately narrow R boundary around UW's directory-backed
`bayesTFR` and `bayesLife` objects. The rest of the project remains Python.

The reader requires **R 4.4.2** and **Rtools44**. `bootstrap.R` installs
dependencies from the CRAN snapshot dated 2024-11-11. It installs the two
serialized-object readers from immutable official UW Git commits, checks their
byte lengths and SHA-256 fingerprints, and refuses to continue unless they are
exactly `bayesTFR` 7.4-4 and the pre-CRAN GitHub release `bayesLife` 5.3-0 used
to create the archive.

```powershell
$env:RTOOLS44_HOME = 'C:\path\to\rtools44'
$rscript = 'C:\path\to\R-4.4.2\bin\Rscript.exe'
& $rscript --vanilla r\uw-extract\bootstrap.R
python scripts\export_uw_fixture.py --rscript $rscript
```

The Python command verifies and unpacks the source archives, invokes
`extract_one_country.R`, checks every exported row and fingerprint, and keeps
the source's 2023 anchor separate from the model's 2024-forward trajectories.
