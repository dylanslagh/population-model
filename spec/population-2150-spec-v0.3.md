# World Population Model to 2150 — Project Specification

*Working spec. Version 0.3, August 2026.*

---

## 0. Purpose of this document

This is a design brief for an interactive world map backed by a Bayesian demographic
projection model running to 2150. It records the reasoning behind the design choices,
not just the choices themselves, because the reasoning is the part that will need
revisiting when new data arrives.

If you are an AI assistant picking this up cold: read §3 (philosophy) before §5
(architecture). The architectural decisions only make sense in light of what the
project is trying to be, and several of them look wrong if you assume the goal is
forecast accuracy. It isn't.

---

## 1. Project overview

**Artifact.** An interactive world map. Click a country, see its population pyramid
(historical and projected), plus projected population at 2100 and 2150 under a set of
named scenarios.

**Purpose.** Test competing hypotheses about long-run human population trajectories.
2150 is chosen deliberately: it is roughly the horizon at which the consequences of
decisions made by people currently alive become visible, and it is beyond where any
institutional forecaster is willing to publish.

**Cadence.** Updated when new high-quality data is released. Every vintage preserved
and scored. The track record is the point.

**Audience.** Numerate generalists — people who know who Jaynes is, broadly
rationalist/EA-adjacent. Secondary audience: future AI systems evaluating which
forecasting approaches were well-calibrated. That second audience drives several
infrastructure requirements in §9.

**Explicit non-goal.** Beating the UN on near-term accuracy. They will win at 2050 and
that is fine. See §3.3.

---

## 2. What we are up against

### 2.1 The UN model

UN World Population Prospects uses a Bayesian hierarchical model, implemented in the
open-source R packages `bayesTFR`, `bayesLife`, `bayesMig`, and `bayesPop` (Ševčíková,
Raftery, Alkema et al., University of Washington).

Fertility is modelled in three phases:

- **Phase I** — pre-transition, high fertility.
- **Phase II** — the fertility transition, a double-logistic decline.
- **Phase III** — post-transition, an **AR(1) process mean-reverting to a
  country-specific long-run level**, with a hierarchical prior across countries centred
  near 1.85.

**The critical observation:** the assumption is not "there is an asymptote." It is
**stationarity**. The Phase III model asserts that post-transition fertility is a
mean-reverting stochastic process. That parameter is estimated from roughly forty years
of data on the handful of countries that completed their transition early — mostly
Europe — and then extrapolated over 130 years to every country on earth.

This is the single most consequential assumption in global demography and it is doing
almost all the work in any projection past 2060.

### 2.2 Why the long-run fertility process dominates everything

A useful shorthand is the **net reproduction rate (NRR)**: roughly, how many daughters
the average woman leaves to the next generation after accounting for the sex ratio at
birth and survival. An NRR of 1 means exact generational replacement; below 1 means each
generation is smaller than the one before it. Under low mortality, replacement is around
a TFR of 2.1. From 2024 to 2150 is only a little over four generations, but repeated
small differences compound dramatically.

| Long-run TFR | NRR   | Multiplier over 4.2 generations |
|--------------|-------|---------------------------------|
| 2.12         | 1.00  | 1.00×                           |
| 1.85         | 0.873 | 0.565×                          |
| 1.50         | 0.708 | 0.235×                          |
| 1.30         | 0.613 | 0.128×                          |

An asymptote of 1.85 versus 1.30 is a **4.4× difference in world population at 2150**,
from a parameter nobody can measure and for which no country has been post-transition
long enough to provide evidence about century-scale behaviour.

**Design implication:** by 2150 essentially nobody alive today is still alive. The
entire population descends from people not yet born. The answer is therefore dominated
by the **long-run fertility process**: whether fertility mean-reverts, remains stably low,
keeps being pushed downward by development, or is eventually pulled upward by selection
and intergenerational transmission. Precision in the base data is nearly irrelevant;
precision about the mechanism is everything.

### 2.3 Alternative approaches worth knowing

- **IHME (Vollset et al., *Lancet* 2020).** Dropped the mean-reversion, drove fertility
  off educational attainment and met need for contraception. Result: **8.8 billion at
  2100 against the UN's 10.4 billion.** Same data, same century, ~1.5 billion apart,
  entirely from model structure. Useful as an existence proof that structure dominates.
- **IIASA / Wittgenstein Centre.** Expert elicitation plus education-driven convergence.
  Produces the SSP population scenarios. Also stops at 2100.
- **UN long-range projections to 2300.** Exists, but it is a 2004 report built on the
  2002 revision. Far too stale to use. Its constant-fertility scenario reaches
  **244 billion by 2150** — worth keeping as an absurdity check (see §8.4).
- **Evolutionary/selection models** (Kolk, Collins, Cesarini and others). One important
  class in which stabilisation or rebound can be *derived* rather than imposed. This is
  one core branch of the project, but it should compete with a second mechanistic
  possibility: that continued economic and social development keeps moving the fertility
  environment downward. See §6.

---

## 3. Design philosophy

### 3.1 Gelman, not Jaynes

The audience framing is "people who know who Jaynes is." The *methodological* target is
Gelman.

This matters because the two want different things from a prior. Jaynes wants it derived
from symmetry and constraints. Gelman's position is that there is no such thing as an
uninformative prior, that priors should encode domain knowledge, and that they are
disciplined through prior predictive simulation and model expansion.

**Maximum entropy is not usable as the foundation here.** MaxEnt over what? Uniform on
TFR ∈ [0,10]? On log TFR? On NRR? Each gives a wildly different 2150 distribution and
there is no transformation group that picks one. MaxEnt does not dissolve the theory
problem; it relocates it into the choice of reference measure and constraint set.

MaxEnt is fine as a *component* — given moment constraints from the observed
post-transition distribution, it yields the least-committal distribution consistent with
them. It is not the backbone.

**The Gelman move that actually earns its keep: prior predictive checks.** Before
touching any data, sample from the prior and inspect the implied distribution of 2150
world population. If it places meaningful mass on 244 billion or on 300 million, the
prior is broken and you knew it without a single observation. On a problem where data
cannot discipline you for a century, this is most of the discipline available.

**Charter document:** Gelman & Shalizi, "Philosophy and the Practice of Bayesian
Statistics" (*British Journal of Mathematical and Statistical Psychology*, 2013). Their
argument — that Bayesian practice is properly hypothetico-deductive rather than
inductive, that you build a model, derive consequences, check them, and *discard* the
model when checks fail rather than accumulating belief — is essentially this project's
methodology written down.

### 3.2 Mechanistic, not phenomenological

The UN's Phase III model **has no referent**. It does not say people will have 1.85
children *because* of anything. It says the time series behaves like a mean-reverting
process. There are no entities and no mechanism, so there is nothing that could be wrong
for a reason. It sits entirely on the associational rung: it cannot answer "what happens
if Korea does X," because there is no causal structure to intervene on.

Consequently it can only ever be wrong *numerically*. When it misses, you learn a number.

A mechanistic model can be wrong *diagnostically*. Miss the rebound and you have learned
that transmission is lossier than twin studies suggest, or that the environmental push
outruns selection. Same miss, vastly more information.

**This is the actual competitive advantage.** Not accuracy — information content per unit
of being wrong.

### 3.3 Lakatos: the UN programme is degenerating

The UN revises every two years, silently absorbing each surprise into refitted
parameters, never stating what would have counted as a refutation. The biennial revision
*is* an ad hoc auxiliary hypothesis machine. It never risks anything, so it never learns
anything.

A progressive research programme predicts novel facts and stakes something on them. This
project can: name the mechanism, derive what it implies for cohort fertility of the
1990s birth cohorts, and publish before the data lands. That is severity in Mayo's sense
— a test that would probably have been failed had the model been wrong.

### 3.4 Where our institutional advantage actually lies

We cannot beat the UN on data. They have the statistical office relationships, the DHS
programme, census microdata. We cannot beat them at 2050; they are very good at that.

The advantage is **institutional freedom**. A UN publication is a political document with
member states in the room. It cannot print "Korea: 8 million" or "Nigeria: 550 million."
Part of why WPP stops at 2100 is that going further would require saying things no
intergovernmental body can say. We have no such constraint.

Three real gaps in the market:
1. Nobody publishes a live, maintained model past 2100.
2. Nobody keeps score on demographic forecasts.
3. The people who would care about both are underserved.

All three are gaps of institutional nerve, not technical difficulty.

### 3.5 Accuracy is not the criterion

Copernicus predicted planetary positions *worse* than the refined Ptolemaic system for
decades, until Kepler replaced circles with ellipses. He won on structure long before he
won on fit.

If this model is off by a billion at 2100 but was wrong in a way that taught someone what
to change, it beat the alternative on the axis that matters.

---

## 4. Data

### 4.1 Primary source

**UN World Population Prospects 2024** (population.un.org/wpp). 237 countries and areas,
1950 to present with projections to 2100. Contains everything a cohort-component model
needs:

- Population by single year of age and sex
- Age-specific fertility rates
- Life tables / survival ratios
- Sex ratio at birth
- Net migration by age and sex

**The next revision has been pushed from 2026 to 2027**, so WPP 2024 is stable for at
least another year. Pin to it explicitly and make the version a first-class field in
every stored output.

Single-age files are large. Preprocess into per-country JSON at build time; do not ship
raw CSVs to the browser.

### 4.2 Posterior access — the important one

The UW group publishes **converged MCMC objects for the WPP2024 fertility and life
expectancy models**, plus migration rate trajectories, as direct downloads alongside
`bayesTFR` / `bayesLife` / `bayesMig` / `bayesPop`.

This is a real posterior that can be conditioned on, reweighted, or have its priors
replaced. If "multi-decade Bayesian update" is the goal, this is the foundation.

Two caveats:
- These are **UW products, not UN products** — they will not exactly reproduce published
  WPP figures.
- They are large; the annual TFR object is around 1.7 GB.

### 4.3 Secondary sources, in order of leverage

1. **Human Fertility Database** (MPIDR/VID) — ~35 countries with clean vital
   registration. **Cohort completed fertility and parity progression ratios.** This is
   the highest-value dataset in the project after WPP, because period TFR conflates
   postponement (recoverable) with quantum decline (not), and the entire Phase III
   argument lives on that distinction. The UN has also recently published a technical
   paper deriving cohort fertility from WPP.
2. **Human Mortality Database** — ~40 countries, single-year age/period/cohort. Enough to
   fit Lee-Carter or coherent Li-Lee independently rather than accepting UN e0
   convergence. Lower leverage than fertility: old-age mortality gains add stock, not
   flow.
3. **Fertility heterogeneity by subgroup** — retention and fertility data for
   high-fertility subpopulations (Haredi, Old Order Amish, Old Colony Mennonite, LDS
   historically). Feeds §6 directly. This is where the mechanism's parameters get pinned.
4. **Wittgenstein Centre / IIASA** — education attainment by age and sex, and the SSP
   scenarios, if an education-driven comparison arm is wanted.
5. **Archived WPP revisions** back to 1963 — required for §9. Digital availability gets
   patchy before the mid-1990s; earlier revisions are scanned volumes.

### 4.4 Where the data is actually messy

Not where you would expect. WPP itself is tidy. The mess is **joining data to map
geometry**:

- Natural Earth polygons and UN country lists disagree on **Kosovo, Taiwan, Western
  Sahara, Palestine**, French overseas departments, and numerous small territories.
- Historical boundary changes if pre-2000 pyramids are displayed: Sudan/South Sudan
  (2011), USSR and Yugoslavia successor states, Serbia/Montenegro.

**Requirement:** maintain an explicit crosswalk table. Treat any unmatched code as a
**build error**, never a silent drop.

### 4.5 Weak-data countries — do not grey them out

There are no gaps in WPP. Estimates exist for Eritrea, North Korea, Lebanon, Somalia,
Afghanistan, DRC. But some are modelled from very thin inputs — Lebanon's last full
census was 1932, DRC's 1984, Eritrea has never conducted one.

**Requirement:** a separate data-confidence layer (last census year, DHS coverage,
vital registration completeness) rather than greying countries out. More honest and more
interesting than a blank polygon.

---

## 5. Architecture

### 5.1 Fork at 2024, not 2100

**Critical.** If WPP's 2100 age structure is used as the base year, the UN's fertility
assumptions have been silently inherited for 76 years and the project's own hypotheses
only operate on the final 50. That defeats the purpose.

Run the model from 2024 forward with consistent assumptions end to end.

### 5.2 The deterministic core

State vector: population by single year of age (0–100+) × sex × country. Optionally ×
type (see §6).

**Plain English:** imagine one very large spreadsheet with a row for every country, age,
sex, and — in the mechanistic version — fertility or social type. The projection engine
simply moves people through that spreadsheet one year at a time.

Each year:
1. Age everyone up one bucket, multiplied by survival ratio.
2. Births = Σ over ages 15–49 of (women at age *a* × ASFR at age *a*).
3. Split newborns by sex ratio at birth.
4. Add net migration by age and sex.

Programmers call this a **Leslie-matrix projection**. The important point for the reader
is simpler: this step contains **no theory about future fertility**. It is just demographic
bookkeeping once the fertility, mortality, and migration assumptions have been supplied.

### 5.3 The dimensionality collapse — for the baseline model

For the ordinary demographic projection, most of the uncertainty can be reduced to **two
main trajectories per country: fertility and mortality**. A fertility schedule spreads the
country's total fertility rate across childbearing ages, while a mortality model turns life
expectancy into survival rates by age.

That simplification is what makes the baseline model tractable, and it is broadly similar
to the UN approach.

The mechanistic model in §6 deliberately adds a small number of extra state variables:
population composition, parent-to-child persistence in fertility-related traits, movement
between social groups, and a **changing fertility environment**. The last term is important:
selection can make high-fertility dispositions more common while economic and social change
simultaneously makes a given disposition produce fewer actual births.

The project should therefore keep two questions separate:

- **Who is becoming more common?** This is the selection and transmission problem.
- **How many children does a person of a given type have under current conditions?** This
  is the economic, institutional, and cultural environment problem.

Those extra variables are not needed to do demographic accounting; they are needed to test
*why* fertility might stabilize, rebound, remain low, or continue falling.

### 5.4 Two-stage fitting — do not skip this

**Do not put the Leslie matrix inside the sampler.**

- **Stage 1:** fit the fertility, mortality, development-pressure, transmission,
  retention, and group-transition model in Stan or NumPyro.
- **Stage 2:** draw from the posterior, push each draw through the deterministic
  projection.

This is what `bayesPop` does. It is the difference between a model that fits overnight
and one that never converges.

### 5.5 Bayesian structure

Hierarchical across countries: country-level parameters are related rather than estimated
as if every country were a separate universe. Data from countries with long, clean records
can therefore inform countries with shorter or noisier histories, without forcing them to
behave identically. This is partial pooling in the Gelman sense.

Observed births, fertility, mortality, retention, and subgroup estimates should all carry
**measurement uncertainty** rather than being treated as exact facts. That is especially
important for weak-data countries (§4.5) and for the subgroup parameters in §6, where
sample sizes may be small.

The output should be distributions, not single best guesses. Each run should generate many
internally consistent demographic histories, so the project can answer questions such as
"how often does world population peak before 2100?" or "how often does selection produce
a meaningful fertility rebound by 2150?" rather than only printing one line on a chart.

---

## 6. The mechanistic layer

### 6.1 Two live mechanisms, not one

**Dead end: simple ecological population biology.** Carrying capacity, density dependence,
logistic growth. Human fertility *falls* as resources become abundant. The demographic
transition is precisely the anomaly that broke every simple Malthusian model. Importing
that machinery produces confident errors.

Two mechanistic branches are worth keeping alive:

**Evolutionary demography.** Do people who have more children systematically pass on some
of the traits, preferences, institutions, or social identities that helped produce that
higher fertility? If so, population composition changes over generations instead of
fertility being an external number imposed on everybody forever.

**The changing fertility environment.** Does economic and social development keep changing
the relationship between people's underlying desire or propensity for children and the
number they actually have? If the opportunity cost of parenthood keeps rising, fertility
can continue falling even while selection pushes population composition in the opposite
direction.

Neither mechanism should be granted victory in advance. The central long-run question is
how they interact. The UN's Phase III time-series model cannot directly represent that
competition because neither population composition nor the causal fertility environment is
part of its state.

### 6.2 Do not treat "heritability" as one thing

The model should separate at least three channels of parent-to-child persistence:

1. **Genetic predispositions.** Fertility-related traits can be partly influenced by many
genes. Offspring resemble their parents, but only imperfectly, and recombination creates
new variation.
2. **Family and cultural transmission.** Preferences about family size, marriage,
religiosity, gender roles, contraception, and the value placed on parenthood can also be
transmitted from parents and communities to children.
3. **Group membership.** A child can remain in the group in which they were raised,
leave it, join another group, intermarry, or retain some of its fertility norms after
formally leaving.

These mechanisms can be correlated, but they are not interchangeable. In particular,
**"heritability" should be reserved for the genetic component**. When the project means
the combined tendency for high- or low-fertility behavior to persist across generations,
call it **intergenerational fertility persistence**.

This distinction matters because the three channels operate on different timescales.
Genetic evolution over the four or so generations to 2150 may be real but modest. Cultural
transmission and group retention can move much faster.

One of the motivating empirical results from the original design should stay in the model:
**Kohler and colleagues found that the estimated genetic contribution to fertility
variation increased across Danish cohorts during the demographic transition** (Kohler et
al. 1999, 2002). One interpretation is that as contraception and individual choice became
more available, differences between people's dispositions had more room to show up in
completed family size. That is suggestive rather than decisive, but it is exactly the kind
of observation a mechanistic model should try to explain rather than smooth away.

### 6.3 The core selection argument, in plain English

Suppose two sets of parents differ persistently in completed family size. If the parents
who have more children also tend to raise children who, on average, have somewhat more
children themselves, then their descendants become a larger share of the next generation.
That happens automatically; no long-run fertility floor has to be assumed in advance.

But selection changes **population composition**, not the surrounding environment. A
population can become more weighted toward people who would prefer larger families while
actual fertility still falls if the economic and social cost of having children rises even
faster. This distinction should be explicit throughout the model.

The important empirical quantities are therefore not simply today's fertility differences.
They are the combination of:

- how large the fertility difference is;
- how much of that difference survives into the children's generation;
- how long the effect persists after children leave a community or marry outside it;
- how the surrounding economic and social environment changes the number of children a
  person with a given fertility propensity actually has; and
- whether selection changes population composition faster or slower than that environment
  is moving.

This is the sense in which stabilization, rebound, or continued decline can be *derived*
rather than imposed.

### 6.4 Group membership should be a transition process, not a permanent label

The first implementation can still use a small number of discrete types, because that is
transparent and computationally manageable. But "retention" should eventually mean more
than a single probability that a child either stays or becomes mainstream.

For every parental type, the model should allow several adult outcomes: remain in the
same type, move into the mainstream, move into another type, or occupy an intermediate
state after intermarriage or partial assimilation. In implementation this is just a table
of transition probabilities: for children raised in group A, what fraction become A, B,
or mainstream adults?

Retention should also be allowed to vary *within* a group. Children from highly committed
families may have very different adult retention rates from children on the group's
margin. That avoids treating a religious or cultural population as internally uniform.

### 6.5 The mainstream population is not a residual bucket

Selection should also operate inside the general population. Otherwise the model would
implicitly say that intergenerational fertility persistence exists only in visibly
high-fertility communities.

A simple first version can divide the mainstream into a few latent fertility-propensity
types — for example low, middle, and high — without attaching ethnic, religious, or
political labels to them. Children would have an elevated probability of ending up near
their parents' type, but with substantial movement between types each generation.

This lets the model capture the possibility that ordinary high-fertility lineages become
more common even if no named subgroup expands dramatically. It also gives defectors from
high-fertility communities somewhere more realistic to go: they may lose the group label
while retaining part of the fertility profile for a generation or two.

### 6.6 A toy group example — retention is load-bearing

Keep the existing intuition, but present it as a **toy demonstration rather than a
forecast**. Imagine a group that begins as 1% of the population, averages about six
children per woman, and retains 90% of children into the next generation, while the
surrounding population averages about 1.4 children.

Using the deliberately simplified assumptions in the original calculation, the small
group grows by roughly two-and-a-half times per generation while the surrounding
low-fertility population shrinks. After about four generations, the toy calculation can
put the group near **70% of the descendant population**. That number should not be shown
as a prediction — the assumptions would almost certainly change long before then — but it
is an excellent demonstration of the compounding mechanism.

The important result is that **retention and parent-to-child persistence are as
consequential as fertility itself**. This also explains why groups with superficially
similar fertility can follow very different trajectories. A community with somewhat
lower fertility but very high retention can outgrow a community with higher fertility
whose children mostly converge toward the surrounding population.

### 6.7 Parameters must be allowed to change as groups grow

A dangerous version of the model would take the fertility and retention of a small,
unusual population today and extrapolate them unchanged after that population becomes
10%, 30%, or 60% of society.

The model should therefore allow fertility, retention, intermarriage, and assimilation to
respond to context. A group's behavior may change as it urbanizes, becomes wealthier,
runs into housing or partner-market constraints, builds larger institutions, or simply
stops being socially unusual. The surrounding mainstream may also change in response.

Economic development matters here too. A high-fertility group can retain strong family
preferences while nevertheless having fewer children as education lengthens, earnings rise,
housing becomes more expensive, or the career cost of interrupting work increases. In
other words, **retaining the preference is not the same thing as retaining the realized
fertility rate**.

This should initially be handled through scenarios rather than dozens of free parameters.
For example:

- **Constant-trait scenario:** today's fertility and retention differences persist.
- **Convergence scenario:** differences shrink as a group becomes larger or more
  integrated.
- **Institutional persistence scenario:** strong internal institutions preserve much of
  the difference even at larger scale.
- **Development-pressure scenario:** underlying family preferences persist more strongly
  than observed fertility because the opportunity cost of realizing those preferences
  continues to rise.

The comparison between those scenarios is itself scientifically interesting.

### 6.8 The honest problem — where is the rebound?

There is evidence that completed fertility shows intergenerational persistence and that
both genetic and cultural transmission contribute to it. A naive selection story would
therefore predict that high-fertility dispositions should gradually become more common.

The original specification made this tension especially concrete. A rough application of
the standard evolutionary-demography calculation, using twin-study estimates around 0.2
for the genetic component and the observed spread in completed family size, suggests an
increase on the order of **0.3 children per generation** if the other conditions of the
calculation held. Do not make the reader follow the equation; keep the numerical
implication because it creates a useful model check.

If that simple calculation were the whole story, a rebound should already be becoming
visible. **It is not.** That is the central empirical problem, not an inconvenience to
hide.

At least four explanations are plausible:

1. Parent-to-child persistence in actual fertility is weaker than estimates from some
   twin or family studies would suggest.
2. Selection is real, but the **fertility environment is moving downward faster**. Rising
   opportunity costs, later partnership formation, longer education, housing constraints,
   and changing expectations about what good parenthood requires can reduce realized
   fertility even while higher-fertility dispositions become more common.
3. Generation length is increasing, so selection acts more slowly in calendar time.
4. Selection is occurring, but mostly in population composition or completed cohort
   fertility and has not yet become visible in period TFR.

The model must make these possibilities explicit. It should not assume that the missing
rebound is merely delayed. **One legitimate outcome is that selection never catches the
moving environmental target by 2150.** Which explanation dominates is one of the main
things the project is trying to learn.

### 6.9 Development pressure is a mechanism, not a residual trend

The project should not treat "fertility keeps falling with development" as a black-box
trend line. If continued development is going to compete with selection, the model should
say **what about development is doing the work**.

The most useful concept is the **opportunity cost of parenthood**. As economies develop,
people can face more valuable or more demanding alternatives to spending time on child
rearing: longer education, steeper career ladders, higher foregone earnings, more leisure
and consumption options, later partnership formation, expensive housing in productive
cities, and higher expectations for time and money invested in each child. Institutions
can offset some of those costs, but there is no reason to assume that they will fully do
so.

Do not reduce this to GDP per capita. GDP is an upstream summary, not the mechanism. The
model should eventually use a small set of observable proxies for the fertility
environment, such as:

- age at completion of education and entry into stable work;
- earnings and the parenthood-related interruption to earnings or career progression;
- housing costs relative to income, especially in high-productivity cities;
- age at first partnership, marriage, and first birth;
- childcare availability and time costs;
- the amount of time and money parents typically invest per child; and
- social norms around what counts as an acceptable level of investment in children.

The first implementation does not need all of these. A small development-pressure index
with broad uncertainty is preferable to a large fragile model. The key requirement is
conceptual: **the mapping from fertility propensity to actual births must be allowed to
change over time**.

Do not make this layer a disguised assumption that "higher GDP always means lower
fertility." The relationship may weaken, saturate, reverse under different institutions,
or differ sharply across countries. Those possibilities should be represented through
hierarchical estimates and explicit scenario paths rather than a single permanent slope.

Nor does the project need a detailed macroeconomic forecast to 2150. For the long horizon,
use a small number of transparent development paths — for example, opportunity costs keep
rising, flatten, or are substantially offset by institutions — and propagate uncertainty
through each. This keeps the fertility mechanism visible instead of hiding it inside a
speculative economic model.

This creates a clean competition between forces. Selection may shift the population toward
people who, under a fixed environment, would have more children. Development may shift the
environment so that every type has fewer children than the same type would have had a
generation earlier. The observed fertility path is the result of both.

Mean reversion is therefore not the default state that the other mechanisms perturb. It is
one hypothesis about the net result. The model should be capable of learning or producing
all of the following without changing its basic architecture: rebound, stable very-low
fertility, slow continued decline, or a decline that eventually reverses when selection
becomes strong enough.

### 6.10 The anti-epicycle rule

Mechanistic models can be *less* honest than transparent curve fits. A model with a
fertility parameter, a retention parameter, a cultural-persistence parameter, and an
assimilation parameter can fit almost anything if all four are tuned against the same
fertility series.

**Rule: pin every mechanism parameter to independent evidence whenever possible.** Use
retention studies to estimate retention, family and twin studies to constrain genetic
persistence, longitudinal surveys to estimate parent-child resemblance, and fertility
histories to estimate the distribution of completed family size. Do not use the same
outcome series both to invent the mechanism and to declare that the mechanism fits.

If a parameter cannot be estimated independently, it is a **scenario knob** and must be
labelled as one in the UI and in the output metadata.

### 6.11 What the Bayesian model is doing here

The point of making this Bayesian is not to decorate the project with probability
notation. It is to admit that almost every important mechanism is uncertain.

Instead of saying "retention is 82%" or "the mainstream parent-child persistence is
0.4," assign a plausible range to each quantity, informed by whatever evidence exists.
Then simulate many possible futures. Countries and groups with strong data get estimates
mostly driven by their own evidence; weakly measured groups are pulled toward patterns
seen in comparable populations rather than being allowed to produce absurd estimates.

Each simulated future should carry the entire chain with it: fertility differences, the
changing fertility environment, retention, movement between groups, mainstream fertility
persistence, mortality, and migration. The output is therefore not merely a distribution for world population in
2150. It is a distribution over **different demographic histories and population
compositions**, which lets the project ask why two futures with the same population total
arrived there by different mechanisms.

---

## 7. Empirical constraints the model must respect

These are hard-won observations that constrain the hypothesis space. Any scenario that
violates them needs an explicit defence.

### 7.1 Period TFR is a bad test statistic — two independent demonstrations

**Korea, 2023–2026.** TFR fell to 0.72 in 2023, then rose: 0.75 (2024), 0.80 (2025),
with **Q1 2026 at 0.95** and officials expecting the annual figure to exceed 0.9 for the
first time since 2019. On its face, mean reversion vindicated.

But the mechanism is not what the theory needs. Marriages jumped **14.9% in 2024 — the
largest increase since records began in 1970** — partly pandemic-postponed weddings
finally occurring, partly a relatively large cohort of women now in their early-to-mid
30s. The cohorts behind them are much smaller, capping how long the rebound can run.
That is tempo recovery plus favourable age structure, not a change in quantum.

**China, 2000–2016.** The apparent plateau was artificial. The one-child policy was
*binding* for many families who wanted two, so each relaxation (rural two-child,
selective two-child 2013, universal two-child 2016) released pent-up demand and produced
small bumps. Simultaneously the 1980s echo cohort kept the number of prime-age women
high. Both props vanished around 2016–2017, revealing a TFR that had been far below
replacement for years. Marriage rates fell sharply at the same time, which in a country
with very low non-marital fertility translates almost directly into fewer births.

**Conclusion:** period TFR moves for structural, policy, and age-composition reasons
unrelated to the parameter being modelled. **Score against cohort fertility.** A model
scored on period TFR will be credited for noise.

### 7.2 Cash incentives are not the same thing as the opportunity cost of parenthood

South Korea has spent **over $200 billion on pronatalist policy since 2006** — cash
bonuses, subsidised childcare, housing benefits, parental leave — without a durable return
to high fertility. China's pivot from restriction to encouragement likewise did not
produce a durable return to high fertility.

That is important evidence against a simple story in which a modest subsidy can purchase a
large fertility response. But it **does not put a hard ceiling on economic explanations**.
A cash payment is only one small component of the lifetime economic and time cost of a
child. The relevant opportunity cost may include years of foregone earnings growth,
career interruption, delayed partnership, expensive housing, reduced leisure and
flexibility, and increasingly intensive expectations for parental investment.

The model should therefore distinguish two claims:

- **Short-run price responsiveness:** how much births move after a subsidy, tax credit, or
  childcare reform.
- **Long-run development pressure:** how much the entire environment of education, work,
  housing, partnership, and parenting changes the fertility associated with a given set of
  preferences.

Evidence that the first is weak does not imply that the second is weak. The project should
estimate or scenario-test them separately.

### 7.3 The gender-equity rebound theory failed its own best test

McDonald's argument — that fertility recovers once institutional gender equity catches up
with individual-level equity — had the Nordics as its showcase. They reached ~1.9 around
2010 with the most generous parental leave and childcare regimes on earth, then fell to
the 1.3–1.4 range, Finland lower still.

The theory's best case, under its own best conditions, failed. This evidence is already
in; no waiting required.

### 7.4 No confirmed precedent for recovery from sub-1.2 without immigration

As of this writing there is no clear historical case of a country recovering from
sub-1.2 fertility to near replacement absent immigration. Korea's current rise is the
first serious candidate counterexample and is **actively resolving** — see §7.1 for why
it probably does not count yet.

**This is a live, dated test.** Track it.

### 7.5 The lag structure: decline is fast-moving, not slow-moving

The damage locks in the moment a cohort underreproduces, regardless of later policy
correction. Smaller cohorts produce fewer absolute births even at higher per-capita
rates — compound interest in reverse. Absolute population declines slowly; the annual
birth *flow* collapses fast.

This is the thesis that makes 2150 a referendum on the present, and it is what the map
is for.

---

## 8. Scenarios to implement

The most important design change in Version 0.3 is that **development pressure and
selection are not mutually exclusive scenarios**. They are two forces that can operate at
the same time. The scenario system should therefore be built from two axes, then exposed
through a small number of named presets in the UI.

### Axis A — the fertility environment

1. **Mean reversion.** Post-transition fertility is pulled back toward a stable long-run
   level, roughly reproducing the UN Phase III logic.
2. **Stable low fertility.** No meaningful rebound, but the downward environmental shift
   eventually stops; fertility settles at a low level.
3. **Continued development pressure.** The opportunity cost and social environment of
   parenthood keep shifting downward, so a person with the same underlying fertility
   propensity tends to have fewer children in later cohorts.

### Axis B — intergenerational selection and transmission

1. **Off.** Population composition does not feed back into fertility. This reproduces the
   logic of conventional projections.
2. **Mainstream persistence only.** High- and low-fertility tendencies persist imperfectly
   within the ordinary population, with no explicit named groups.
3. **Full transmission model.** Mainstream persistence plus genetic transmission,
   family/cultural transmission, group retention, intermarriage, defection, and
   assimilation as described in §6.

The UI should ship with a handful of interpretable presets rather than every possible
combination:

1. **UN-equivalent.** Mean reversion + selection off. Reproduce it faithfully so
   differences are attributable.
2. **Development-pressure baseline.** Continued development pressure + selection off.
   This is the clean test of whether long-run decline can emerge without any evolutionary
   feedback.
3. **Selection rebound.** Stable or weakening development pressure + full transmission.
   This is the strongest version of the hypothesis that selection eventually pushes
   fertility upward.
4. **Race between development and selection.** Continued development pressure + full
   transmission. This is the project's most important mechanistic scenario: high-fertility
   dispositions and groups can become more common while observed fertility still falls.
   The central output is **whether and when selection overtakes the downward environmental
   shift**.
5. **Stable-low equilibrium.** Development pressure weakens and selection is present, but
   the two approximately offset one another at a persistently low fertility level.
6. **Gender-equity rebound.** Institutional equity convergence drives recovery. Currently
   disfavoured by §7.3 — include it anyway, and let it lose on the record.
7. **Constant fertility.** Absurdity check only. Should reproduce ~244 billion by 2150;
   if it does not, the projection engine has a bug.

Scenario 7 doubles as an engine unit test. Every substantive scenario must ship with a
named mechanism, parameter sources, a falsifiable implication, and a resolution date.

---

## 9. Scoring and versioning infrastructure

**This is the contribution. The model is replaceable.**

If future AI systems are a real audience, the valuable artifact is not the 2150 number —
that is unfalsifiable within the author's lifetime. It is a **scored track record with
methodology attached**. A model in 2070 should be able to ask "which prior structure over
fertility was best calibrated across five decades" — a question nobody can currently
answer, because the UN revises biennially and never scores itself.

Requirements:

- **Preregistered predictions** with a proper scoring rule — log score or CRPS.
- **Immutable versioning.** Every vintage stored, never silently overwritten. Git-tracked
  model code alongside the predictions it generated.
- **Machine-readable output.** Priors, likelihood, and parameter provenance explicit in
  the stored artifact, not just in prose.
- **Score the mechanism, not the endpoint.** Cohort fertility for the 1990s birth cohorts
  is the first real grade; world population at 2150 is not scoreable in any useful
  timeframe.
- **Low maintenance cost by design.** The value accrues only if the project survives
  decades. Every dependency is a liability.

---

## 10. Build order

**Phase 1 — Backtest harness (build this first).**
Archived WPP revisions in, scoring rule out. "Here is how wrong each vintage was, and
about what." Self-contained and useful even if the forward model is never built, and it
is the scaffolding everything else hangs on.

Known systematic failures to expect and quantify:
- African fertility: the UN assumed decline would follow the Asian/Latin American path;
  it stalled. Population under-projected.
- East Asian fertility: assumed a floor near replacement; actual reached 0.7.
- Mortality: life expectancy gains systematically under-projected for sixty years running
  (cf. Oeppen & Vaupel 2002, "Broken Limits to Life Expectancy").

A visible "here is how wrong this class of model was last time" panel does more for
reader calibration than any confidence interval.

**Phase 2 — Deterministic engine.** Leslie matrix, WPP 2024 inputs, reproduce the UN
medium variant to 2100 as a correctness test. Constant-fertility scenario must hit
~244 billion at 2150.

**Phase 3 — Map and pyramids.** Crosswalk table, data-confidence layer, per-country JSON.

**Phase 4 — Bayesian layer.** Two-stage fitting. Start from the UW MCMC objects rather
than from scratch.

**Phase 5 — Mechanistic layer.** Group transitions, mainstream fertility persistence,
separate genetic/cultural transmission channels, and the development-pressure layer in
§6.9. Parameters pinned per §6.10.

**Phase 6 — Scoring and preregistration.** Though the file formats should be fixed in
Phase 1.

---

## 11. Timeline of resolution

| Date        | What resolves |
|-------------|---------------|
| ~2027       | WPP 2027 revision — first data update, first scoring event |
| 2026–2028   | Whether Korea's rebound holds or reverts as the large cohort passes through |
| 2025–2045   | Sub-Saharan African fertility trajectory — largest near-term uncertainty for 2100 |
| **~2038**   | **Completed cohort fertility for women born in the early-to-mid 1990s. Tempo versus quantum resolves. The first real grade.** |
| 2100        | Interesting, not decisive |
| 2150        | Not scoreable by anyone now alive |

If completed cohort fertility for the 1990s cohorts in Korea and Spain lands at 1.3–1.4,
much of the current period-TFR collapse was postponement, but that **does not establish**
a century-scale return toward 1.85. It would only show that the period collapse overstated
the decline in completed family size. If completed fertility lands near 1.1, quantum
decline is real and the standard Phase III mean-reversion story is in much deeper trouble.

This is therefore a clean test of **tempo versus quantum**, not a complete test of the
long-run asymptote. The development-versus-selection question resolves more slowly and
should be scored through successive cohorts rather than declared won after one rebound.

---

## 12. Open questions

- Which explanation in §6.8 for the missing rebound carries the most weight? In
  particular, is selection weak, merely slow, or being outrun by a fertility environment
  that is still moving downward?
- How persistent is fertility within the ordinary mainstream population once income,
  education, geography, and family background are separated out?
- How should children of mixed-type couples be handled? A simple average may be wrong if
  one parent's community or family culture dominates transmission.
- How quickly do defectors converge toward mainstream fertility? Immediate convergence is
  probably too strong; permanent retention of the old fertility pattern is also too
  strong.
- How strongly should fertility and retention be allowed to change as a high-fertility
  group becomes a much larger share of society? This is likely one of the biggest sources
  of 2150 uncertainty.
- Migration is close to unforecastable beyond a few decades. It cancels globally but
  dominates country-level results for rich countries. **The UI must state that
  world-level 2150 figures mean something and country-level ones mean much less.**
- Is generation length stretching fast enough to materially delay selection effects? This
  is measurable now and currently under-examined.
- Which observable variables best capture the opportunity cost of parenthood without
  turning the development-pressure layer into a kitchen-sink regression?
- Does the relationship between development and fertility keep shifting as countries move
  beyond today's income frontier, or does it eventually saturate? This is a central 2150
  uncertainty and cannot be learned directly from current data.
- Should the education-driven (IIASA/SSP) arm remain a separate comparison model, or is it
  sufficiently represented inside the development-pressure axis?

---

## 13. References

- Gelman & Shalizi (2013), "Philosophy and the Practice of Bayesian Statistics" —
  methodological charter.
- Gelman et al. (2020), "Bayesian Workflow."
- Alkema et al. (2011); Raftery et al. (2014) — the UN Phase II / Phase III models.
- Ševčíková & Raftery — `bayesTFR`, `bayesLife`, `bayesMig`, `bayesPop` documentation.
- Vollset et al. (2020), *Lancet* — the IHME alternative projection.
- Kohler, Rodgers & Christensen (1999, 2002) — heritability of fertility across Danish
  twin cohorts.
- Oeppen & Vaupel (2002), "Broken Limits to Life Expectancy."
- National Research Council (2000), *Beyond Six Billion* — retrospective assessment of
  forecast accuracy.
- Human Fertility Database (MPIDR/VID); Human Mortality Database.
- UN DESA, *World Population Prospects 2024*.

---

## 14. Standing instructions for AI assistants working on this repo

1. **Never fit a mechanism parameter to the series it is meant to explain.** If it cannot
   be sourced independently, mark it a scenario knob.
2. **Never silently overwrite a stored prediction vintage.**
3. **Never treat WPP estimates as ground truth** — model observation error.
4. **Never score against period TFR.** Cohort fertility only.
5. **Fail loudly on unmatched country codes.** Never drop a country silently.
6. **Run prior predictive checks before fitting.** If the prior implies 244 billion or
   300 million, stop.
7. **Do not optimise for forecast accuracy at the expense of structural transparency.**
   That trade is the whole point of the project, and it goes the other way.
8. **Do not make mean reversion the default merely because it is conventional.** Keep
   population composition and the fertility environment as separate moving parts, and
   allow continued development pressure to outrun selection if the evidence supports it.
