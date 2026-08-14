# Mechanism parameter audit

Audited 2026-08-13. This is the durable source trail for
`data/reference/mechanism_parameters.csv`. It records what the cited evidence
actually supports, which values changed, and which rows must remain scenario
knobs or unverified estimates. URLs are links to the publisher, author
repository, statistical agency, or specialist demographic center; no value was
fit to this model's population or fertility output.

## Result

Seven of the eight sourced rows are now checked. The five scenario knobs remain
unverified by definition. `mainstream_propensity_cv` also remains unverified:
the original evidence was only a recollection of the distribution of completed
family size, not a reproducible calculation from cohort-parity data.

| Parameter | Decision | Source-backed finding |
|---|---|---|
| `mainstream_persistence` | Verified; keep 0.15 | Recent parent-child fertility correlations are usually about 0.1-0.2. |
| `mainstream_propensity_cv` | **Not verified** | Plausible, but no source in the old row permits the CV to be reproduced. |
| `group_retention_haredi` | Verified; 0.90 -> 0.867 | 13.3% overall leaving implies 86.7% retention; faction variation is large. |
| `group_fertility_haredi` | Verified; keep 6.40 | CBS estimate is 6.38 for 2020-2022, conventionally rounded to 6.4. |
| `group_share_haredi` | Verified; 0.135 -> 0.139 | 1.392 million, or 13.9% of Israel in 2024. |
| `group_retention_amish` | Verified; 0.87 -> 0.845 | Population-wide age-40+ retention is 84.46%. |
| `group_fertility_amish` | Verified; 5.50 -> 6.10 | Population-wide 2002-2011 snapshot TFR is 6.1. |
| `group_share_amish` | Verified; 0.00120 -> 0.00115 | 394,720 U.S. Amish residents in 2024. |

## Mainstream persistence

The old central value survives, but its rationale is narrower and cleaner than
the old row suggested. It should be based on observed intergenerational
fertility continuity, not on a twin-study heritability estimate. Heritability is
a variance decomposition and is not numerically interchangeable with a
parent-child correlation.

- Michael Murphy, "Is the Relationship between Fertility of Parents and
  Children Really Weak?" (1999), DOI
  [10.1080/19485565.1999.9988991](https://doi.org/10.1080/19485565.1999.9988991),
  reports correlations mostly 0.15-0.20 in the recent large British and U.S.
  samples it reviews and values around 0.2 for 1960s childbearing.
- Michael Murphy, "Cross-National Patterns of Intergenerational Continuities in
  Childbearing in Developed Countries" (2013), DOI
  [10.1080/19485565.2013.833779](https://doi.org/10.1080/19485565.2013.833779),
  uses 46 populations in 28 countries. Its unweighted regional means for
  respondents aged 40+ are 0.09 in Northern America, 0.11 in Northern Europe,
  0.15 in Western Europe, 0.17 in Southern Europe, and 0.19 in Eastern Europe.
  The [open manuscript is held by LSE](https://researchonline.lse.ac.uk/54523/).
- Kohler, Rodgers, and Christensen (1999), DOI
  [10.1111/j.1728-4457.1999.00253.x](https://doi.org/10.1111/j.1728-4457.1999.00253.x),
  supports the existence and cohort-dependence of genetic influence, but its
  reported 30-50% variance components in selected female cohorts do **not**
  identify this model's combined persistence coefficient.

The 0.15 center is therefore verified. The 0.05-0.30 simulation interval is a
deliberately conservative cross-setting range rather than a confidence interval
reported by one paper.

## Mainstream propensity dispersion

This row is still the highest-leverage empirical gap. Published parity tables
show substantial variation around mean completed family size, but the old claim
that a mean of 1.8-2.0 and standard deviation of 1.1-1.3 imply a CV near 0.6 was
not tied to a cohort, country, table, or reproducible transformation.

Do not mark it verified from a TFR series or fit it to the rebound the mechanism
is intended to explain. Compute it from completed cohort family-size
distributions, preferably across multiple low-fertility countries and cohorts.
The [Human Fertility Database](https://www.humanfertility.org/) and the
[Cohort Fertility and Education Database](https://www.eurrep.org/database/)
are the natural next sources. The calculation should state treatment of the
open highest-parity category and distinguish women from families or couples.

## Haredi parameters

### Retention

Gabriel Gordon and Eitan Regev's Israel Democracy Institute study,
["Transitions Between Religious Groups among Israeli Jews"](https://en.idi.org.il/articles/32775)
(2020), estimates that 13.3% of people aged 20-64 who grew up Haredi had left,
implying 86.7% retention. It also reports strong faction differences: leaving
rates of 5.4% for Hasidim, 8.6% for the Lithuanian faction, and 26.4% for
Sephardim. That evidence does not support the old 0.97 upper bound for the whole
population. The revised 0.735-0.950 interval reflects observed faction
heterogeneity, not sampling uncertainty around the overall estimate.

The outcome is current Haredi identification. It is not identical to belief,
religious observance, school enrollment, or retention of some fertility norms
after leaving. The separate defector parameter exists for that reason.

### Fertility and population share

Israel CBS's
[*Births and Fertility - Main Indicators, 2022*](https://www.cbs.gov.il/he/publications/doclib/2020/%D7%9C%D7%99%D7%93%D7%95%D7%AA-%D7%97%D7%992019/lidot_all_index_1.pdf)
reports Haredi TFR of 6.38 for 2020-2022. The Israel Democracy Institute's
[Annual Statistical Report on Haredi Society 2024](https://en.idi.org.il/media/27532/idi-annual-statistical-report-on-haredi-society-2024.pdf)
rounds this to 6.4 and documents a decline from 7.5 in 2003-2005. The same report
estimates 1.392 million Haredim in 2024, 13.9% of Israel's population. These
support 6.40 and 0.139 at the model's 2024 fork.

The fertility number initializes a relative named-group propensity. It remains
inappropriate as a score for the model's long-run cohort-fertility mechanism.

## Amish parameters

Cory Anderson and Stephanie Thiehoff, "The population structure of the Amish,
a rapidly growing ethnic religion in North America" (2025), DOI
[10.1080/00324728.2025.2592576](https://doi.org/10.1080/00324728.2025.2592576),
is the strongest source found: a population-wide analysis of more than 50,000
households. The [open full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC12909094/)
reports:

- TFR 6.1 from 77,073 births in a 2002-2011 snapshot;
- 84.46% retention among people aged 40+, which the authors identify as the
  best approximation to lifetime retention; and
- substantial age, cohort, and affiliation differences that argue against
  treating retention as a constant of nature.

For the starting share, the Young Center for Anabaptist and Pietist Studies'
[Amish Population, 2024](https://groups.etown.edu/amishstudies/population-2024/)
estimates 394,720 U.S. residents. Against the approximately 344 million U.S.
population used at the model fork, this is 0.115%. The Young Center definition
includes horse-and-buggy Amish groups and excludes Beachy Amish and Amish
Mennonites; the model inherits that boundary.

## Scenario knobs

The following rows remain `kind=knob, verified=FALSE`, as required by the
anti-epicycle rule:

- `mainstream_types`
- `defector_high_propensity_weight`
- `development_decline_per_decade`
- `development_floor`
- `group_convergence_per_generation`

No literature check can turn a structural choice or an explicitly future path
into a verified estimate. If independent evidence later identifies one, change
its definition and provenance explicitly rather than merely flipping the flag.
