# Mechanism parameter audit

Audited and completed 2026-08-13. This is the durable source trail for
`data/reference/mechanism_parameters.csv`. It records what the cited evidence
actually supports, which values changed, and which rows must remain scenario
knobs or unverified estimates. URLs are links to the publisher, author
repository, statistical agency, or specialist demographic center; no value was
fit to this model's population or fertility output.

## Result

All eight sourced rows are now checked. The five scenario knobs remain
unverified by definition. The final gap, `mainstream_propensity_cv`, is now a
reproducible calculation from pinned cohort-parity data rather than a recalled
rule of thumb.

| Parameter | Decision | Source-backed finding |
|---|---|---|
| `mainstream_persistence` | Verified; keep 0.15 | Recent parent-child fertility correlations are usually about 0.1-0.2. |
| `mainstream_propensity_cv` | Verified; 0.60 -> 0.57, range 0.44-0.80 | Median completed-family-size CV across 19 low-fertility countries is 0.570; an independent U.S. estimate is 0.695. |
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

The old 0.60 was numerically plausible but unsupported. It is replaced by 0.57,
calculated without fitting to any model output.

### Primary calculation

The source is the
[Cohort Fertility and Education Database](https://www.eurrep.org/database/database/)
(CFE). `scripts/fetch_cfe.py` pins the latest displayed source for 45 countries;
43 have a single observation year and support the age window. France and Italy
pool surveys across years and are excluded rather than assigned an invented
date. The committed manifest records URLs, byte counts, and SHA-256 hashes.
Following the [CFE terms](https://www.eurrep.org/database/about/terms-of-use/),
the original tabulations remain gitignored and are not redistributed.

`scripts/analyze_cfe_dispersion.py` applies the same declared rule everywhere:

- women, not couples or only mothers;
- children ever born, including childless women;
- whole birth-cohort bins whose members were all aged 50-59 at observation;
- one estimate per country, with education categories summed and country-
  documented unknown-parity conventions retained;
- a low-fertility comparison set declared as mean completed fertility at or
  below 2.2 children, not selected for agreement with the model.

The open highest-parity cell does not have to be pretended equal to its lower
bound. CFE supplies exact total children, so its mean is identified. The primary
estimate assigns geometric excess above the open parity—the maximum-entropy
integer distribution with that mean. Across all 43 countries, using this tail
instead of the minimum-variance integer tail changes the CV by 0.005 at the
median and at most 0.059. A deliberately extreme sensitivity places the tail on
its lower bound and 40 children; its larger widths are reported, not hidden.

Among the 19 low-fertility countries (29.1 million reported women), the
country-median CV is **0.570**, with observed country range **0.443-0.787** and
country 10th-90th percentiles **0.466-0.710**. The women-weighted median is
0.555, but the unweighted country median is the parameter center: these sources
are a set of plausible settings, not a harmonized global sample, and weighting
would let the Russian extract dominate. The range rounds outward to 0.44-0.80.

As an independent check, paired CDC/NCHS
[Cohort Fertility Tables 2 and 3](https://www.cdc.gov/nchs/nvss/cohort_fertility_tables.htm)
give mean completed fertility 2.040 and CV **0.695** for U.S. cohorts 1947-1956
at exact age 50. This is inside the declared range and above the cross-country
median. `scripts/fetch_cdc_cohort.py` pins both official files and their hashes.

### What the parameter means

The parity marginals do **not** identify a latent biological or cultural trait
with CV 0.57. Realized family-size variation includes timing chance,
infertility, partnership histories, environment, and measurement. Hruschka and
Burger (2016), DOI
[10.1098/rstb.2015.0155](https://doi.org/10.1098/rstb.2015.0155), show with 200
surveys that substantial completed-fertility variance can arise from a counting
process without stable differences among women. They also find that the lowest-
fertility samples often depart from Poisson toward targeted family sizes. That
is visible here: most low-fertility CFE distributions are underdispersed
relative to Poisson, so subtracting a Poisson variance would be an invalid way
to manufacture a latent-trait CV.

The model instead uses 0.57 as an **effective phenotypic spread**, jointly with
the observed intergenerational correlation. Fertility-weighting changes the
offspring generation's mean by

`Cov(parent completed fertility, offspring completed fertility) / mean parent fertility`.

When the marginal variances are equal, the relative change is `correlation ×
CV²`. That is exactly the one-generation response produced by this model's
CV-and-persistence construction. The pair therefore moment-matches an observed
covariance; it does not claim that every source of family-size variance is
inherited. Higher-generation behavior and the three-bin lognormal shape remain
structural approximations, which is why `mainstream_types` stays a scenario
knob and the broad empirical CV range is propagated.

### Projection sensitivity

`scripts/analyze_mainstream_cv_sensitivity.py` propagates the evidence without
refitting anything. In the central “race” scenario, changing the superseded
0.60 to 0.57 lowers the 2150 population from 7.749 to **7.610 billion** and the
selection effect from 1.190 to **1.174**. Holding every other parameter fixed,
the empirical CV endpoints 0.44 and 0.80 produce 7.104 and 8.920 billion. The
center correction is modest; cross-setting dispersion uncertainty is not. The
committed JSON records the same comparison for mainstream-only and full
selection under the UN environment.

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
