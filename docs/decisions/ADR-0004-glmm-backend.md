# ADR-0004 — Beta-binomial mixed model backend

**Kind:** METHODOLOGY

**Status:** PROPOSED — AWAITING RESEARCHER APPROVAL. **Q8 is now settled by fact:** the cluster probe (2026-09-25) confirms R is absent, so glmmTMB is not available and PyMC is the only option.
**Date:** 2026-09-11

## Context
§4.11 specifies a beta-binomial mixed model and instructs that the fitting
procedure be documented exactly. The canonical tool, `glmmTMB`, is R-only; R is
absent locally and unknown on the cluster. Python has no mature frequentist
beta-binomial GLMM with nested random effects.

## Decision (proposed)
Fit in **PyMC**: beta-binomial likelihood, fixed effects per §4.11, random
intercepts for `schema/constraint` and `domain`, weakly informative priors
documented in the preregistration. Report posterior means and 95% credible
intervals. There is **no cross-check available**: R does not exist on either machine, so
the paper must report the PyMC fit alone and say why.

The confirmatory claim is unaffected either way: §4.11 gives precedence to the
cluster bootstrap, and the GLMM carries only secondary and exploratory analyses.

## Consequences
* Bayesian intervals are credible intervals, not confidence intervals; the paper
  must say so rather than blur the two.
* Priors become preregistered quantities.
* The `(1 | domain)` term has only 5 levels — at the lower bound for a random
  effect. The variance estimate is reported with that caveat attached.
