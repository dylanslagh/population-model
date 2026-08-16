# 02. A hierarchical model, and the case for development pressure

**chat** &middot; 2026-08-08 to 2026-08-08 &middot; 7 messages from Dylan, 12 from the model, 0 tool calls.

> Tool output and model reasoning are omitted; see [README](README.md) for what that leaves out and why.

---

### Dylan

give me an example of a andrew gelman style bayesian model

### Model

A very Andrew Gelman–style Bayesian model would usually be hierarchical, partially pooled, generative, and focused on estimating variation across groups rather than just producing a single coefficient.

For example, suppose we want to estimate how much a tutoring program improves students’ test scores across 50 schools. Students are randomly assigned to tutoring or control, but we expect the effect to differ somewhat by school.

A simple hierarchical model might be:

y_ij ~ Normal(mu_ij, sigma)

where student i is in school j, and

mu_ij = alpha_j + beta_j T_ij.

Here T_ij = 1 if the student received tutoring and 0 otherwise. Each school gets its own baseline score alpha_j and its own treatment effect beta_j.

The distinctly Gelman-ish move is that we don't estimate those 100 parameters independently. Instead, schools are treated as draws from a population of schools. A school with lots of observations can have an estimated treatment effect largely determined by its own data; a small school with noisy results gets partially pooled toward the overall treatment effect.

We might put weakly informative priors on the overall baseline, overall treatment effect, residual variation, and between-school variation, plus a reasonable prior on the correlation between school intercepts and treatment effects.

Imagine the raw results looked like this:

School | Students | Raw tutoring effect
A | 400 | +4.8
B | 350 | +5.5
C | 20 | +13.0
D | 18 | -5.0

A classical approach that estimates each school separately might tempt you to say that tutoring is enormously successful in C and harmful in D. The hierarchical Bayesian estimates might instead come out roughly:

A = 4.9
B = 5.3
C = 7.1
D = 2.0

with an overall effect around 4.8.

The small schools' spectacular-looking effects get pulled toward the population mean because the model learns that much of the apparent variation is sampling noise. But they aren't forced to equal the population mean either. That's partial pooling, probably the single most characteristic feature of Gelman's applied Bayesian modeling.

Then you wouldn't stop at saying, "the posterior mean is 4.8." You'd ask substantive questions such as the probability the average treatment effect is positive, or the posterior probability that tutoring actually hurts students in a particular school.

You might also estimate the between-school standard deviation, which tells you something scientifically interesting: tutoring effects genuinely vary between schools, rather than treating that variation as an annoyance.

And very much in Gelman's style, you'd do posterior predictive checks: generate replicated datasets from the fitted model and compare them with the observed data. Does the model reproduce the distribution of school means? The unusually high and low scores? The amount of variation between schools? If not, revise the model.

The whole conceptual structure is therefore:

students -> schools -> population of schools

rather than either pretending all schools are identical or analyzing 50 schools as completely unrelated experiments.

This is basically the worldview behind a huge amount of Bayesian Data Analysis: build a probability model corresponding to the data-generating structure, model heterogeneity explicitly, regularize through partial pooling, and evaluate the model by asking whether it can reproduce the important features of the data.

If you'd like, I can also give you a more characteristically Gelman example involving election polling, where multilevel regression and poststratification (MRP) makes the philosophy particularly concrete.

### Dylan

would it be possible to model world population in 2100 with this kind of model? what would the inputs be?

### Model

Yes. In fact, world population in 2100 is almost tailor-made for a Gelman-style hierarchical Bayesian model, because the uncertainty is not mainly about today's population; it is about future fertility, mortality, and migration trajectories that differ by country but are related across countries.

The natural starting point would not be a simple regression, but a Bayesian cohort-component model. You would model each country's population by age and sex, then advance it through time according to births, deaths, and migration.

The Bayesian part enters because fertility, mortality, and migration are themselves uncertain future processes.

The core inputs would therefore be present and historical demographic data:

- population by country, age, and sex
- births and age-specific fertility rates
- deaths and age-specific mortality rates
- life expectancy and survival tables
- net international migration by age and sex
- historical trajectories of all those quantities

You would probably also include predictors that help forecast the demographic rates: women's education, income or GDP per capita, urbanization, contraceptive use, infant mortality, desired family size, age at marriage or first birth, health-system indicators, and perhaps measures of political instability or migration policy. But these aren't strictly necessary. A surprisingly powerful demographic model can be built largely from the historical demographic trajectories themselves.

The particularly Gelman-like part would be hierarchical modeling across countries. Instead of forecasting Nigeria, France, Brazil, and Vietnam completely independently, countries could be partially pooled within regions and regions within the world.

That gives you several levels:

year observations
-> countries
-> regions
-> world.

If you have abundant high-quality demographic data for France, France largely speaks for itself. If data for a small or poorly measured country are noisy, its estimates get pulled toward what has happened in comparable countries rather than producing wild extrapolations.

Fertility would probably deserve the most sophisticated treatment because it is a huge source of uncertainty by 2100. You wouldn't simply say "Nigeria's fertility declines by 0.08 births per woman every year." You could model countries as moving through demographic regimes. The model learns from countries that have already gone through the demographic transition to inform countries currently going through it, while leaving uncertainty about exactly when and how quickly any particular country's fertility will fall.

Once fertility reaches a low level, you might use a different process describing whether it stabilizes around 1.3, 1.7, 2.0, rebounds, and so forth. This assumption becomes extraordinarily important over an 80-year horizon because small differences compound across generations.

Mortality could be handled similarly, while migration would probably be the ugliest piece because it is heavily affected by wars, policy changes, economic shocks, and political decisions.

Then you'd run the model forward thousands of times. Every simulation would generate an internally consistent demographic history for every country. Summing them gives a posterior distribution for world population rather than a single point forecast.

And that's the key conceptual advantage. The output isn't really a prediction of world population; it's a probability distribution over possible demographic histories.

You could then ask genuinely Bayesian questions like the probability that world population exceeds 10 billion in 2100, the probability it is lower in 2100 than in 2050, or the probability India's population is declining by 2070.

A particularly interesting feature is that the starting population barely needs prediction at all. We already know the age structure of the world reasonably well. Quite a lot of the 2100 population uncertainty comes from people who haven't been born yet. That makes fertility assumptions enormously consequential.

This isn't just hypothetical, either: modern probabilistic population forecasting is substantially Bayesian and hierarchical in spirit. The UN's probabilistic projections, for example, have used hierarchical Bayesian models for fertility and mortality rather than simply publishing deterministic high/medium/low scenarios.

If we wanted to build a stripped-down version ourselves, we could get surprisingly far with only five inputs per country: current age structure, fertility, mortality, migration, and perhaps GDP/education, then let the hierarchical structure do much of the rest.

### Dylan

What if we add in evolutionary demography, so modeling heritability of fertility among groups, group retention, and within the general population

### Model

Yes. That would turn the model into something closer to an evolutionary-demographic transmission model, where population composition itself is endogenous rather than merely an input. The important conceptual move is to separate at least three transmission channels that can all make fertility “heritable” across generations: genetic inheritance, cultural/social inheritance, and group membership retention. Those are empirically quite different processes and should not be collapsed into one coefficient.

Suppose individuals belong to latent or observed demographic types. A type could represent a combination of fertility-related traits, family norms, and community membership rather than ethnicity or ancestry.

At the individual level, a useful decomposition would be a latent fertility propensity with three components: inherited genetic influences, vertically or socially transmitted preferences and norms, and non-transmitted environmental influences. Actual fertility would then be generated probabilistically from those components plus age, partnership status, income, education, mortality, and so on.

The genetic component could be modeled quantitatively rather than pretending there is a single "fertility gene." Offspring would tend to resemble their parents, while recombination creates variation. Selection then arises automatically: if people with stronger inherited fertility propensities systematically have more surviving children, those propensities become more common in future generations.

But over the next 75 years, cultural transmission could easily be as important as, or more important than, genetic evolution. A child could inherit some portion of the parents' fertility-related cultural orientation while also being influenced by the surrounding society. A community with strong vertical transmission preserves its fertility norms; one with weak transmission converges more quickly toward surrounding society.

Then add the group-retention mechanism. A community's future size depends not simply on births, but also on survival, the probability children remain in the group as adults, conversion or entry, defection or exit, intermarriage, and migration.

That produces a very interesting interaction. A community with fertility of 3.5 children per woman but only 50% intergenerational retention might grow more slowly than one with fertility of 2.7 and 90% retention. Retention itself can also vary within groups: children from very observant or high-commitment families might have substantially different retention probabilities from marginal members of the same community.

That is much richer than assuming fixed population categories. Groups can grow through fertility, shrink through attrition, gain converts, intermarry, and eventually merge into the general population.

You could simultaneously model within-general-population inheritance of fertility. That's important because otherwise you'd artificially treat high-fertility behavior as something occurring only in discrete communities. In reality, if fertility is even moderately correlated between parents and children—through genes, preferences, family environment, or all three—then high-fertility lineages become progressively overrepresented among descendants.

A stripped-down illustration shows why. Imagine two latent fertility propensities: one averaging 3.0 children and the other 1.5. If parental fertility type had zero intergenerational persistence, the distinction largely washes out each generation. But if offspring have a substantial probability of retaining their parents' fertility orientation, then the descendants of the high-fertility population become increasingly important.

This is essentially a demographic form of selection. Crucially, though, the relevant parameter is not just biological heritability. What matters for forecasting is the total parent-offspring persistence of the phenotype under the future environment.

A Bayesian hierarchical version would be especially appropriate because nearly every important quantity is uncertain. You could estimate intergenerational fertility persistence, group retention, and fertility trajectories while partially pooling poorly measured groups toward broader population patterns.

The 2100 simulation then becomes much more interesting than a conventional population projection. Every simulated person effectively carries an age, sex, country, fertility propensity, perhaps a cultural state, and possibly a community affiliation. They partner, reproduce, transmit traits imperfectly, survive, migrate, and sometimes enter or leave groups. Running the process forward produces not merely a probability distribution for total population, but a joint distribution over population size, composition, fertility, trait distributions, and more.

One especially important result could emerge from such a model: you shouldn't necessarily expect today's low fertility rates to remain evolutionarily neutral indefinitely. If persistent differences in completed fertility exist within populations, traits—genetic or cultural—that predict having more children are mechanically enriched among subsequent generations. The difficult empirical question is how strong that persistence is and whether changing institutions overwhelm it.

So I think the most interesting version of this model would explicitly estimate four things separately: fertility differentials, parent-offspring fertility persistence, group retention/transition rates, and the degree to which those parameters themselves change as groups become larger or encounter different environments. That last piece matters enormously; otherwise the model can accidentally extrapolate a small high-fertility subpopulation as though its present behavior would remain unchanged after it became 10 or 30 times larger.

### Dylan

I had a more extensive discussion with claude, but i liked some of your ideas about the specifics more, can you edit this to include some of your ideas? also keep in mind i’m not technical, mathematical notation doesn’t always land with me

### Model

I’ll revise the spec in place rather than just tacking on a new section. I’ll especially weave in the distinctions between genetic inheritance, cultural transmission, group retention, and within-population fertility persistence, while translating any math-heavy parts into plain-language model rules.

### Model

I’ve read the full spec. The biggest opportunity is §6: it currently jumps fairly quickly from “heritability exists” to discrete high-fertility types, whereas the model will be clearer and more defensible if it explicitly treats genes, family culture, and group identity as separate transmission mechanisms, and lets fertility persistence operate in the mainstream population too rather than only inside named groups.

### Model

One thing I’m correcting in my own first pass: I don’t want to lose Claude’s strongest concrete material, especially the Kohler result and the “why haven’t we seen the rebound yet?” calculation. I’m keeping those, but recasting them as empirical checks in ordinary language rather than making the reader decode the breeder’s equation.

### Model

I revised it as Version 0.2, preserving the original argument while making the evolutionary-demography layer both richer and easier to follow.

The main changes are: separating genetic heritability, cultural/family transmission, and group retention instead of bundling them together; adding fertility persistence within the mainstream population, not just named high-fertility groups; treating group identity as a transition process involving retention, defection, intermarriage, and partial assimilation; allowing fertility and retention to change as groups become larger; making the Bayesian/partial-pooling logic more explicit; and turning several equations into plain-English explanations while keeping useful concrete quantities like the Kohler result, the rough +0.3 children per generation selection calculation, and the extreme 1%-to-~70% toy example.

I also changed §5 slightly because the original claim that everything stochastic collapses to two numbers per country stops being literally true once the evolutionary layer is added.

I treated this as an editorial/model-design pass rather than a fact-check, so I preserved the document's empirical claims rather than independently verifying all of them.

### Dylan

Is there room in this model for the possibility that continued economic growth and the resultant opportunity cost against having children will continue to push fertility rates down? I’m not sure the mean-reversion scenario will hold

### Model

Yes—there should be room for that, and I think it’s important enough that the model should treat it as a competing structural possibility, not just a perturbation around eventual mean reversion. I’m checking how the current spec phrases the long-run fertility process so I can point to exactly where I’d change it.

### Model

Yes. In fact, the current spec already has the beginnings of this in Scenario 2—“mean reversion absent; fertility continues to drift down with development”—but I think it is underdeveloped relative to the selection mechanism. Right now mean reversion and evolutionary selection get fairly explicit mechanisms, while continued economic development is mostly a scenario label.

I would make development-driven fertility decline a first-class mechanism in the model, because it can operate at the same time as selection.

The basic intuition can stay nontechnical. Imagine that every generation experiences two opposing forces:

Selection pressure: people with dispositions, cultures, or group memberships associated with higher fertility leave more descendants, gradually pushing the population toward higher fertility.

Development pressure: economic growth raises the value of people's time, expands attractive alternatives to parenthood, lengthens education and career investment, increases the standard of investment expected per child, and can make interrupting a career increasingly costly. That can push fertility downward.

There is no reason the model has to assume the first eventually wins.

In fact, this produces a much more interesting evolutionary-demographic question. Suppose selection would, all else equal, increase completed fertility by something like 0.2–0.3 children over a generation. But the economic/social environment changes enough over that same generation to reduce completed fertility by 0.4. High-fertility dispositions really are becoming more common, yet observed fertility still falls.

So you could have something conceptually like:

Inherited/family propensity toward children
+ high-fertility group effects
- changing economic opportunity cost of children
+ institutions that make work and children easier to combine
= actual completed fertility

That distinction also helps with the “where is the rebound?” problem in §6.8. One possible answer becomes: selection is occurring, but the environment is moving faster than selection. We therefore shouldn't necessarily expect to see a rebound yet—or ever, if the downward environmental pressure continues.

There is good empirical justification for taking that seriously. The OECD's recent synthesis explicitly identifies rising educational attainment and earnings as increasing the opportunity cost of children, alongside housing costs, labor-market establishment, childcare costs, and changing norms about parenthood. A recent Kearney–Levine review also argues that today's very low fertility in rich countries cannot be reduced to one simple price effect; they emphasize expanded work, consumption, leisure, and lifestyle alternatives alongside changing norms and parenting expectations.

That also makes me want to change one thing in our current §7.2, “Fertility is not very price-elastic.” The Korea pronatalist-policy evidence is useful, but it doesn't really put a “hard ceiling” on this mechanism. A $10,000 subsidy failing to induce another child is not evidence that the opportunity cost of parenthood is unimportant. The economically important cost might be years of career interruption, foregone earnings growth, time, housing, reduced flexibility, or the increasingly intensive investment parents expect to make in each child. Classic economic fertility theory explicitly distinguishes these quantity/quality and opportunity-cost effects.

So I would not use GDP per capita alone as the causal variable. Economic growth is upstream. What we're really interested in are the channels through which development changes the cost and attractiveness of parenthood. Useful inputs would include things like earnings potential, the career penalty associated with parenthood, educational duration, age at labor-market establishment, housing costs relative to income, childcare/time costs, urbanization, age at first birth, childlessness, and possibly measures of how much time and money parents invest per child.

And those effects should themselves be estimated hierarchically. Denmark and Korea shouldn't be forced to have the same relationship between income and fertility. The model can learn a typical development effect while allowing institutions and culture to modify it.

The really interesting model would therefore organize the project around three competing long-run forces:

1. Mean reversion: for whatever combination of behavioral/institutional reasons, very low fertility tends eventually to recover toward some stable level.
2. Development pressure: continuing economic and social development keeps shifting the fertility environment downward.
3. Demographic selection: people and groups with persistently higher fertility become a larger share of subsequent generations.

And importantly, development pressure and demographic selection can operate simultaneously.

That generates several genuinely different futures without hard-coding the answer:

- development weakens -> selection eventually produces a fertility rebound;
- development pressure persists but weakens -> fertility settles at a low equilibrium;
- development and selection roughly cancel -> prolonged stable very-low fertility;
- development keeps outrunning selection -> fertility continues declining well into the 22nd century;
- selection becomes unusually strong -> eventual rebound despite continued economic growth.

This is better than making “mean reversion” the baseline and asking whether evolutionary demography modifies it. Whether a stable fertility mean exists at all becomes something the model is trying to learn.

And that changes how I'd phrase Scenario 2 in our spec. Instead of simply:

“No-floor / low-fertility trap. Mean reversion absent; fertility continues to drift down with development.”

I'd make it a named development/opportunity-cost mechanism and let it run inside the evolutionary scenarios too. Then one of the most important outputs becomes something like: At what point, if any, does selection toward higher fertility become strong enough to overcome the continuing downward environmental trend?

That strikes me as probably the most intellectually interesting question in the whole model.

### Dylan

make the changes you’d like to the spec

### Model

I’m folding the “continued development can keep pushing fertility down” idea into the core model rather than leaving it as a side scenario. I’ll make it interact directly with selection, so the model can produce a rebound, a low-fertility equilibrium, or continued decline without assuming any of those outcomes in advance.

### Model

I found two places where this change matters beyond the scenario list: the empirical-constraints section currently overstates what failed cash subsidies imply, and the 2038 “mean reversion survives” test is too generous to mean reversion. I’m tightening both so the model distinguishes the price of children from the broader opportunity cost of parenthood.

### Model

Done. I made this Version 0.3 and reworked the model so continued development is a genuine competing mechanism rather than just a “no-floor” scenario.

The biggest change is that the model now separates two moving forces: population composition can shift toward higher-fertility dispositions through selection and transmission, while the fertility environment can simultaneously shift downward as the opportunity cost of parenthood rises. Neither is assumed to win. I also changed the scenario architecture into two interacting axes, softened the earlier claim that failed cash subsidies imply weak economic effects, clarified that the 2038 cohort-fertility test only resolves tempo versus quantum rather than proving mean reversion, and added explicit instructions not to make mean reversion the default.

The scenario I think is now most interesting is explicitly called “Race between development and selection.” It allows high-fertility people and groups to become steadily more common while total fertility nevertheless continues falling for decades—or even through 2150—if the environment moves faster.

### Dylan

can you make a .txt transcript of this conversation?

