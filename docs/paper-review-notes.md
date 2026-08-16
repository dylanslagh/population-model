# Paper review notes

Review of *Selection on Fertility, and the Environmental Decline That Would Cancel It*, version 1.0.0 dated 15 August 2026.

These are candidate points for Dylan to consider, not an instruction to implement all of them. They are ordered roughly by importance.

1. **A correlation is being treated as a transmission probability.** Equation 4 uses the reported parent-child correlation, $r$, as though it were the probability of inheriting a type or the regression slope of child fertility on parent fertility. Those quantities coincide only under additional assumptions, including equal variances between generations. In general, $\operatorname{Cov}(X,Y)=r\sigma_X\sigma_Y$, not $r\sigma_X^2$. [Murphy's study](https://www.tandfonline.com/doi/full/10.1080/19485565.2013.833779) reports Pearson correlations; it does not directly estimate the transition probability used by the model.

2. **The covariance is constructed, not "directly observed."** The coefficient of variation and correlation come from different datasets, countries, and cohorts. Multiplying their central values creates a synthetic covariance under assumptions; it does not reproduce a covariance observed in one intergenerational sample. Either estimate the covariance or regression slope from paired data, or soften this central claim substantially.

3. **Matching one intergenerational moment does not validate four generations of dynamics.** Many transition rules can reproduce the same first-generation correlation but compound very differently. The headline should survive several alternative transition matrices calibrated to the same observed moment, not just the chosen "inherit or sample the current population" rule.

4. **The boundary cancels terminal fertility, not the accumulated population effect.** The 1.52% decline makes selection and environmental decline offset in the final fertility-rate year. It does not return the 2150 population to the no-selection counterfactual, because earlier extra births remain. The title, abstract, and "exactly cancels selection" wording should say "cancels the terminal fertility multiplier," and the paper should ideally report a separate population break-even rate.

5. **The 1.82-billion result is not produced by only two measured parameters.** It also depends on the stable-low fertility path, regression toward the current population, three-type discretization, identical age profiles across types, global parameter homogeneity, migration treatment, and the post-2100 extension. Call it a conditional result under the central structural specification.

6. **The benchmark fertility environment needs an explicit definition.** The prose says fertility continues to its "observed floor," but the implementation uses the running minimum of the United Nations' projected path, removing its later rebound. That is neither fully observed nor obvious from the paper. Give the equation, explain what happens after 2100, and plot the benchmark fertility path.

7. **The current-population versus base-year regression choice is too consequential to remain a secondary sensitivity.** It changes the multiplier from 1.174 to 1.072 and the stress-test population by nearly half a billion. Report both versions in the main results and calculate the boundary under each.

8. **The evidence is extrapolated much farther than the prose admits.** The coefficient of variation comes from 19 low-fertility countries, while the transmission literature is concentrated in developed and middle-income populations. Both are then applied to all 237 countries. This should be a major limitation, with regional parameter scenarios if feasible.

9. **Completed family-size variation does not identify fertility timing.** Every type receives the same age-specific fertility shape and differs only by a multiplier. If high-fertility types begin earlier or later, the number of generations completed by 2150 changes. Test alternative generation-time schedules or state this assumption prominently.

10. **The mechanism is demographically two-sex but behaviorally maternal-only.** A child's type comes solely from its mother, with no paternal transmission, assortative mating, or couple formation. Explain why evidence covering both male and female respondents can calibrate that rule, or add a two-parent sensitivity.

11. **The three-bin approximation needs a demonstrated convergence check.** Reproducing the mean and coefficient of variation does not reproduce upper-tail behavior, which may matter disproportionately under selection. Show results for more bins and at least two plausible distribution shapes.

12. **The named-group conclusion overreaches the modeled evidence.** The model includes only the Haredi population in Israel and the Amish in the United States. It supports "these two modeled groups add 0.05 billion," not the broader conclusion that named high-fertility groups collectively contribute only 2.5% as much as mainstream variation.

13. **The Arenberg condition is stated in the wrong units.** Arenberg and colleagues define fertility as a single-sex reproductive rate, with 1 representing replacement, not total fertility rate in children per woman. The relevant condition is that expected surviving daughters who retain the type exceed one, not simply "retention times total fertility rate is greater than one." The cohort engine may implement the correct arithmetic, but the explanation should be corrected. See [Arenberg et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC10355194/).

14. **"Selection overtakes the environment in 100% of draws" is misleading.** The underlying criterion is merely that the selection multiplier exceeds 1.01. That shows selection raises fertility relative to the same environment path; it does not show that selection defeats the 4% decline or restores the benchmark. State exactly what was measured.

15. **The claim that low-fertility countries pass through more generations is unsupported.** Fertility level does not determine generation length; mean age at childbearing does. Demonstrate that relationship from the modeled schedules or remove the explanation.

16. **The 90% parameter bands are sensitivity bands, not probability intervals.** Parameters and scenario knobs are drawn independently and uniformly from judgmental ranges. Those choices create the reported percentiles. Describe them as uniform-range sensitivity results and show which parameters are assumed independent.

17. **Figure 5 compares unlike forms of uncertainty.** Bayesian posterior draws, arbitrary scenario ranges, structural alternatives, and mechanism knobs do not have directly comparable 90% widths. "One-at-a-time sensitivity comparison" would be more accurate than an uncertainty decomposition or attribution.

18. **The historical backtest cannot establish that prior United Nations bands were "too narrow."** The paper acknowledges that the low and high variants had no promised probability coverage. A 35% inclusion rate can show that the scenario envelopes frequently failed to bracket later estimates, but not that they missed a defined calibration target.

19. **"Validated projection to 2150" overstates what was validated.** The accounting engine is impressively reproduced against United Nations outputs through 2100. The 2100-2150 extension is the project's assumption, and the selection mechanism has not been empirically validated. The subtitle should distinguish those three things.

20. **The paper could lose substantial repetition.** The same mechanism, 1.82-billion result, named-group comparison, and 1.52% boundary recur in the abstract, introduction, results, discussion, and conclusion. Cutting roughly 15-20% would make the argument feel more authoritative. The debugging anecdotes are admirable project notes, but several could move to the reproducibility appendix.

21. **Preserve the strongest parts.** The explicit parameter provenance, separation of sourced values from knobs, machine-generated result tables, paired migration comparisons, and disclosure of failed earlier implementations are unusually good. The revision should concentrate that transparency around a narrower set of defensible claims.
