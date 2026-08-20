# Annotation Guideline

Each judgement applies one checklist item to a complete review rather than to an individual sentence or open-coding behaviour.

## Rating Scale

| Label | Meaning | When to use |
| --- | --- | --- |
| `yes` | Clearly met | The review addresses the item clearly, specifically, and relevantly. |
| `partial` | Partially satisfied | The review addresses relevant content, but incompletely, in general terms, only in part, or with insufficiently clear evidence. |
| `no` | Not satisfied | The review does not address the item, or provides only a vague or unusable statement. |
| `not_applicable` | Not applicable | The item is not relevant to the paper type, review form, or current review context. |

`yes`, `partial`, and `no` form a three-level ordinal judgement rather than a
five-point Likert scale. `not_applicable` does not indicate a poor review; it
means that the item should not be scored in the current context.

## Rules for `no` Versus `not_applicable`

First determine whether the item applies to the paper and review context. Only
then evaluate how well the review addresses it.

- Use `yes`, `partial`, or `no` when the item is relevant to the paper and
  review, and an annotator could reasonably expect the review to address it.
- Use `no` when the item is relevant but the review does not address it, or its
  treatment is unusable, incorrect, or too vague to receive credit.
- Use `not_applicable` when the item is not relevant to the paper type, review
  form, or current context, and scoring it would be unfair.
- Do not assign `not_applicable` automatically because the review does not
  mention something. If the review should reasonably have addressed it, assign
  `no`.
- Do not use `not_applicable` merely because the annotator is uncertain. If the
  item is relevant, use `partial` or `no` and record the uncertainty.
- For conditional request items such as `CON_3a` and `CON_3b`, assign `no` when
  the paper has a clear empirical or explanatory support gap but the review
  makes no usable request. Assign `not_applicable` when the paper does not need
  such additional support or has already addressed it adequately.
- When a review makes a relevant but generic request, such as “add more
  experiments” or “provide more analysis”, the appropriate rating is normally
  `partial`, not `not_applicable`.

## Evidence Rules

- Record a brief evidence note for each `yes` or `partial` rating whenever
  possible.
- Long quotations are unnecessary; a short paraphrase of the relevant review
  comment is sufficient.
- When an item requires paper context, consult both the review and the paper.
- The specificity of a suggestion can initially be judged from the review
  alone. Judgements involving factual accuracy, grounding, independence, or
  claim support must be checked against the paper.
- If the same evidence supports multiple items, explain its distinct role under
  each item.

## Dimension Boundaries

- `Coverage`: whether the review attends to the relevant objects and scope of
  the paper or its evaluation setup.
- `Substance`: whether the review evaluates the importance, adequacy, quality,
  or value of those objects.
- `Reasoning`: whether the review examines evidence-to-claim logic, validity
  threats, or the need for further analysis.
- `Grounding`: whether the review's own judgements are supported by manuscript
  evidence or verifiable scholarly context.
- `Constructiveness`: whether the review gives specific, actionable requests
  that can guide revision.
- `Independence`: whether the review offers its own judgement rather than merely
  repeating limitations already stated by the authors.
- `Specificity`: whether feedback is specific and locatable, regardless of
  whether it is praise, critique, or a suggestion.
- `Clarity`: whether the review identifies problems in expression, structure,
  terminology, notation, figures, tables, or technical explanation that affect
  understanding.
- `Ethics`: whether the review addresses relevant ethical, social, safety,
  privacy, release, or environmental concerns.

## Pairwise Boundary Rules

The same review comment may support multiple items, but the rationale for each
item must be distinct.

| Pair | Main distinction | The same evidence can support both when... |
| --- | --- | --- |
| `COV_3` / `SUB_4` | `COV_3` concerns whether the empirical scope covers relevant tasks, datasets, and settings; `SUB_4` concerns whether the existing evidence, baselines, or metrics adequately support the contribution. | The reviewer states that more domains or datasets are needed because the current scope is insufficient to support a generalisation claim. |
| `REA_4a` / `CON_3a` | `REA_4a` concerns whether robustness, ablation, or sensitivity analysis is needed to test a claim; `CON_3a` concerns whether the reviewer makes a specific, actionable empirical request. | The reviewer requests a particular ablation or robustness test and explains which claim it would test. |
| `REA_4b` / `CON_3b` | `REA_4b` concerns whether diagnostic, error, qualitative, or mechanistic analysis could explain why the results occur; `CON_3b` concerns whether the reviewer makes a specific, actionable explanatory request. | The reviewer requests an error analysis or case study and explains how it would illuminate a particular failure or phenomenon. |
| `CON_2` / `SPE_2` | `CON_2` concerns whether the request relates to reproducibility, reporting, setup, or data documentation; `SPE_2` concerns whether a clarification or revision request is precise. | The reviewer precisely requests hyperparameters, preprocessing information, the annotation protocol, data splits, or setup details. |
| `GRO_1` / `GRO_3` | `GRO_1` considers whether all major factual and evaluative judgements are grounded; `GRO_3` focuses specifically on unsupported or hallucinated negative criticism. | The review contains negative criticism whose evidential support needs to be evaluated. |
| `SUB_3` / `COV_2` / `SUB_4` | `SUB_3` concerns only the value of an artifact or resource itself; `COV_2` concerns coverage of the evaluation setup; `SUB_4` concerns the adequacy of empirical evidence. | A dataset, benchmark, or resource is both a paper contribution and part of its evaluation evidence. |

## Checklist Items

### COV_1

**Question:** Does the review identify the paper's main task, contribution,
method, and central claims accurately enough for the rest of the feedback to be
interpretable?

**Context required:** Paper text required.

**Definition:** Determine whether the reviewer demonstrates a basic
understanding of what the paper does, what it contributes, its main method, and
its central claims. A lengthy summary is not required.

**Yes:** The review accurately identifies the main task, contribution, method,
and central claims well enough for the subsequent feedback to be interpretable.

**Partial:** The review accurately identifies only some of these elements, or
its summary is coarse but still demonstrates an understanding of the paper's
subject.

**No:** The review does not identify the subject of the paper or clearly
misunderstands its task, method, or contribution.

**Not applicable:** Use only rarely, when the review form requires no summary
and the subsequent comments can be evaluated independently without one.

**Boundary note:** This is a Coverage item, not an evaluation of the quality of
the contribution. The latter belongs under `SUB_1`.

### COV_2

**Question:** Does the review cover the paper's evaluation setup, datasets or
benchmarks, and main empirical findings when these are relevant?

**Context required:** Paper text required.

**Definition:** Determine whether the review attends to the evaluation setup,
datasets or benchmarks, and main findings of an empirical paper.

**Yes:** The review accurately covers the relevant evaluation setup and main
findings.

**Partial:** The review mentions the evaluation or dataset but omits important
setup details or results, or refers only generally to “experiments” or
“results”.

**No:** The review does not cover the empirical evaluation at all, even though
the paper clearly requires such coverage.

**Not applicable:** Use for conceptual, theoretical, position, or survey papers
without a substantive empirical evaluation.

**Boundary note:** This item asks whether evaluation information is covered.
Whether the evaluation is adequate or well designed is assessed mainly under
`SUB_4` or `REA_2`.

### COV_3

**Question:** Does the review consider whether the empirical scope covers
relevant tasks, datasets, evaluation conditions, and generalisation settings?

**Context required:** Paper text required.

**Definition:** Determine whether the review considers whether the experiments
cover the tasks, datasets, conditions, or generalisation settings that should
reasonably be included.

**Yes:** The review explicitly discusses the adequacy of the empirical scope,
such as task or data coverage, cross-setting evaluation, or generalisation.

**Partial:** The review mentions a scope concern but does not explain why it
affects coverage or generalisation.

**No:** The paper has a clear empirical-scope problem that the review does not
address, or the review only states generally that the evaluation is limited.

**Not applicable:** Use for a non-empirical paper or one that does not call for
a judgement about task, dataset, or generalisation scope.

**Boundary note:** `COV_3` concerns the scope of the empirical evaluation:
whether tasks, datasets, conditions, and generalisation settings are adequately
covered. Whether baselines or comparisons sufficiently support the contribution
is assessed mainly under `SUB_4`. A request for more domains or settings to
support a generalisation claim may provide evidence for both items.

### SUB_1

**Question:** Does the review assess the novelty, significance, motivation, or
gap-addressing value of the work rather than only restating the authors' claims?

**Context required:** Paper text required.

**Definition:** Determine whether the review substantively evaluates the
novelty, significance, motivation, or gap-addressing value of the contribution.

**Yes:** The review explicitly evaluates whether the work is novel, significant,
or well motivated and provides a specific reason.

**Partial:** The review mentions novelty, significance, or motivation, but its
supporting rationale is weak or generic, or it covers only a small part of the
issue.

**No:** The review merely repeats the authors' claimed contribution without
offering its own assessment.

**Not applicable:** Use only rarely; most research reviews should be able to
evaluate the value of the contribution.

**Boundary note:** An unsubstantiated novelty judgement may also raise a problem
under `GRO_2` or `GRO_3`.

### SUB_2

**Question:** Does the review substantively assess the method design, component
rationale, technical depth, simplicity, or implementation choices?

**Context required:** Paper text required.

**Definition:** Determine whether the review evaluates the method's design,
rationale for its components, technical depth, simplicity, or implementation
choices.

**Yes:** The review specifically assesses the method design or a key component.

**Partial:** The review briefly evaluates or characterises the method as, for
example, interesting, simple, or complex, but gives no specific technical
reason.

**No:** The review does not substantively evaluate the method; it only describes
the method or evaluates the results.

**Not applicable:** Use cautiously for papers without a clear methodological
contribution.

**Boundary note:** Accurate description of a method belongs under `COV_1`;
assessment of the quality of its design belongs under `SUB_2`.

### SUB_3

**Question:** Where relevant, does the review assess the value, validity, or
usefulness of datasets, benchmarks, resources, code, models, or other artifacts?

**Context required:** Paper text required.

**Definition:** Apply this item only when a dataset, benchmark, resource, code,
model, system output, or other artifact is itself a substantive contribution,
release, evaluation object, or reusable output of the paper. Determine whether
the review assesses the artifact's value, validity, quality, or usability.

**Yes:** The review explicitly evaluates the artifact's usefulness, validity,
quality, release value, reusability, limitations, or scope of application.

**Partial:** The review mentions the artifact but evaluates it only
superficially, or merely describes it as useful, valuable, or available without
a specific reason.

**No:** The paper makes a clear artifact or resource contribution, but the
review does not evaluate its value or validity.

**Not applicable:** Use when the paper does not present a dataset, resource,
artifact, code, model, or system output as a contribution, release, or
evaluation object. A standard method paper's use of common evaluation datasets,
or ordinary code availability, does not by itself make `SUB_3` applicable.

**Boundary note:** `SUB_3` may apply when the paper explicitly presents released
code, a model, a system, or a resource as a contribution. If code is only
replication material, it is normally considered under `CON_2`. Coverage of
ordinary evaluation datasets is assessed mainly under `COV_2/COV_3`, while the
adequacy of empirical evidence is assessed mainly under `SUB_4`.

### SUB_4

**Question:** Does the review judge whether the relevant baselines, comparisons,
metrics, or empirical evidence are adequate for supporting the paper's
contribution?

**Context required:** Paper text required.

**Definition:** Determine whether the review assesses whether the empirical
support—including relevant baselines, comparisons, metrics, or other
evidence—is adequate for the paper's contribution.

**Yes:** The review assesses the adequacy of the paper's most important
empirical support and explains its reasoning.

**Partial:** The review evaluates only a minor component, or identifies a
baseline or evidence problem without making its importance clear.

**No:** The paper clearly depends on empirical evidence, but the review does not
assess whether its evidence, baselines, comparisons, or metrics are adequate.

**Not applicable:** Use for a non-empirical paper or when the contribution does
not depend on empirical evidence.

**Boundary note:** This is an adequacy judgement: whether the existing
baselines, comparisons, metrics, or evidence sufficiently support the
contribution. Whether experiments cover enough tasks or settings belongs mainly
under `COV_3`; a specific request for an additional experiment may also be
assessed under `CON_3a`.

### REA_1

**Question:** Does the review check whether major claims follow from the
evidence, results, and internal logic of the paper?

**Context required:** Paper text required.

**Definition:** Determine whether the review examines whether the paper's major
claims are supported by its evidence, results, and internal logic.

**Yes:** The review explicitly judges whether a claim is supported by the
evidence or identifies a claim as overstated or insufficiently supported.

**Partial:** The review mentions claim support without being specific, or
evaluates only a minor claim.

**No:** The paper has an evidence-to-claim problem that the review does not
examine, or the review evaluates only whether results are favourable without
assessing the logic of the claim.

**Not applicable:** Use only rarely; most research papers make claims.

**Boundary note:** Whether the reviewer's own criticism is grounded belongs
under `GRO_1/GRO_3`; whether the paper's claim is supported belongs under
`REA_1`.

### REA_2

**Question:** Does the review evaluate the appropriateness of metrics,
measurement choices, statistical analysis, human evaluation, or construct
operationalisation?

**Context required:** Paper text required.

**Definition:** Determine whether the review evaluates the validity of the
paper's measurements, metrics, statistical analysis, human evaluation, or
construct operationalisation.

**Yes:** The review explicitly discusses whether a metric, measurement,
statistical analysis, human evaluation, or construct operationalisation is
appropriate.

**Partial:** The review mentions a metric or evaluation concern without giving
a specific validity-based reason.

**No:** The paper clearly depends on measurement choices, but the review does
not assess their appropriateness.

**Not applicable:** Use when the paper does not involve relevant metrics,
measurements, statistics, human evaluation, or construct operationalisation.

**Boundary note:** Whether a baseline is sufficiently strong belongs mainly
under `SUB_4`; whether a metric measures the intended construct belongs mainly
under `REA_2`.

### REA_3

**Question:** Does the review identify confounds, unfair comparisons,
alternative explanations, or threats to causal or comparative interpretation?

**Context required:** Paper text required.

**Definition:** Determine whether the review identifies confounds, unfair
comparisons, alternative explanations, or threats to causal or comparative
interpretation.

**Yes:** The review explicitly identifies a possible confound, unfair
comparison, or alternative explanation.

**Partial:** The review implies that a comparison is unfair or an interpretation
is problematic but does not explain the specific threat.

**No:** The paper contains a clear threat to interpretation that the review does
not address.

**Not applicable:** Use when the paper makes no relevant causal or comparative
claim or interpretation.

**Boundary note:** Requesting an additional robustness check may belong under
`REA_4a`; explaining why the existing comparison is unfair belongs under
`REA_3`.

### REA_4a

**Question:** Does the review assess or request ablations, robustness checks, or
sensitivity tests that would test whether the paper's claims hold?

**Context required:** Paper text required.

**Definition:** Determine whether the review evaluates or requests an ablation,
robustness check, sensitivity test, or similar analysis that would test the
stability of a claim.

**Yes:** The review explicitly evaluates or proposes an ablation, check, or test
that would assess the robustness of a claim.

**Partial:** The review generally asks for more experiments or robustness
analysis without specifying what should be tested.

**No:** A paper's claim requires robustness, ablation, or sensitivity evidence,
but the review neither evaluates the existing analysis nor requests such
evidence.

**Not applicable:** Use when the paper type is unsuited to an ablation,
robustness, or sensitivity test, or when the paper has already addressed the
issue adequately and there is no reasonable need for an additional test.

**Boundary note:** `REA_4a` may receive `yes` when the reviewer evaluates an
existing ablation or robustness analysis, even if no new analysis is requested.
`CON_3a` considers only whether the reviewer makes a specific empirical-support
request.

### REA_4b

**Question:** Does the review assess or request diagnostic, error, qualitative,
or mechanistic analyses that would explain why the results occur?

**Context required:** Paper text required.

**Definition:** Determine whether the review evaluates or requests a diagnostic,
error, qualitative, or mechanistic analysis intended to explain why the results
occur.

**Yes:** The review explicitly requests or evaluates an error analysis, case
analysis, mechanistic explanation, or diagnostic breakdown.

**Partial:** The review generally asks for more analysis or explanation without
specifying the type of analysis required.

**No:** The results or claims clearly require diagnostic or explanatory
analysis, but the review neither evaluates the existing analysis nor requests
additional analysis.

**Not applicable:** Use when explanatory analysis is not needed or is clearly
irrelevant to the paper, or when the paper already provides an adequate
explanation and there is no reasonable need for further diagnostic or
explanatory analysis.

**Boundary note:** This item concerns a reasoning need: whether diagnostic,
error, qualitative, or mechanistic analysis would help explain the results or
claims. An assessment of an existing error analysis can therefore support
`REA_4b`; whether a request is specific and actionable may also be assessed
under `CON_3b`.

### GRO_1

**Question:** Are the review's factual claims and evaluative judgements grounded
in specific paper content, reported results, figures, tables, or examples?

**Context required:** Paper text required.

**Definition:** Determine whether the review's own factual and evaluative claims
are supported by evidence from the paper or other verifiable context. This
includes positive judgements, negative judgements, and neutral factual
statements.

**Yes:** The review ties its main judgements to specific paper content, results,
figures, tables, or examples.

**Partial:** The review provides some evidence, but some judgements remain
unsupported or overly general.

**No:** The review makes factual or evaluative claims without visible evidence,
or its claims conflict with the paper.

**Not applicable:** Use only rarely, when the review contains almost no factual
or evaluative judgement.

**Boundary note:** `SPE_1` concerns whether feedback is specific and locatable;
`GRO_1` concerns whether all major judgements are supported and non-fabricated,
not only whether criticism is supported.

### GRO_2

**Question:** Are novelty, related-work, and positioning judgements grounded in
concrete prior work, baselines, citations, or scholarly context?

**Context required:** Paper text and scholarly context where available.

**Definition:** Determine whether judgements about novelty, related work, or
positioning are supported by prior work, baselines, citations, or scholarly
context.

**Yes:** The review explicitly connects its novelty or positioning judgement to
relevant work, a baseline, a citation, or scholarly context.

**Partial:** The review mentions prior work or novelty, but the evidence is not
specific or the context is limited.

**No:** The review asserts that the paper is not novel, omits related work, or is
poorly positioned without giving a specific basis.

**Not applicable:** Use when the review makes no judgement about novelty,
related work, or positioning.

**Boundary note:** Evaluation of novelty as a contribution belongs under
`SUB_1`; whether that novelty judgement is grounded belongs under `GRO_2`.

### GRO_3

**Question:** Does the review avoid unsupported or hallucinated criticisms by
tying negative feedback to evidence in the manuscript or verifiable scholarly
context?

**Context required:** Paper text required.

**Definition:** Evaluate specifically whether negative criticism is unsupported
or hallucinated, with particular attention to this failure mode in LLM-generated
reviews. When the review contains no negative criticism, normally use
`not_applicable`.

**Yes:** The review's negative feedback is generally supported by manuscript
evidence or verifiable context.

**Partial:** Some criticism is supported, but some negative claims lack evidence
or over-interpret the paper.

**No:** The main negative criticism is unsupported, clearly hallucinated, or
inconsistent with the paper.

**Not applicable:** Use when the review contains no negative criticism.

**Boundary note:** `GRO_1` assesses grounding in general; `GRO_3` is narrower and
considers only the risk of unsupported or hallucinated negative criticism. The
same critique may affect both items, but record a separate rationale for each.

### CON_1

**Question:** Are the review's suggestions actionable, concrete, and tied to the
specific issue being raised?

**Context required:** Review text is usually sufficient; paper text is helpful.

**Definition:** Determine whether the review's suggestions are specific,
actionable, and connected to the issue identified.

**Yes:** Suggestions clearly explain what the authors could do and relate to a
specific issue.

**Partial:** The review gives suggestions, but they are general—for example,
“improve clarity” or “add experiments”—and lack sufficient operational detail.

**No:** The review makes no suggestion, or its suggestions are not actionable or
are disconnected from the identified issue.

**Not applicable:** Use when the review makes no revision request or suggestion
and the review form does not call for one.

**Boundary note:** `CON_1` evaluates overall suggestion quality. Whether a
suggestion requests empirical or explanatory support is assessed under
`CON_3a` or `CON_3b`, respectively.

### CON_2

**Question:** Does the review request concrete missing details needed for
reproducibility, method reporting, setup clarification, or data documentation?

**Context required:** Paper text required.

**Definition:** Determine whether the review requests specific missing
information needed for reproducibility, method reporting, experimental setup,
or data documentation.

**Yes:** The review identifies the specific setup information, methodological
or reporting detail, or documentation that is missing and explains why it is
needed.

**Partial:** The review asks for more detail or better reproducibility but does
not state precisely what is missing.

**No:** The paper has a clear reporting or documentation gap that the review
does not address, or the review says only “more details” without identifying
what is needed.

**Not applicable:** Use when reproducibility, reporting, setup clarification,
and data documentation are not relevant to the paper type or review context and
there is no reasonable reporting gap.

**Boundary note:** `CON_2` concerns whether the request is about reproducibility,
method reporting, setup clarification, or data documentation; `SPE_2` concerns
whether the request is precise. “Provide the training hyperparameters” may
support both items. “Revise the motivation section” may support `SPE_2`, but
normally not `CON_2`.

### CON_3a

**Question:** When asking for more empirical support, does the review specify
concrete additional experiments, baselines, comparisons, or robustness checks
rather than generic additions?

**Context required:** Review text is usually sufficient; paper text helps
determine relevance.

**Definition:** When the review asks for further empirical support, determine
whether it specifies which experiments, baselines, comparisons, or robustness
checks should be added.

**Yes:** The review proposes a specific empirical addition, such as a particular
type of baseline, comparison, dataset, or robustness check.

**Partial:** The review merely asks for more experiments or evaluation without
specifying what should be added.

**No:** The paper or the review itself reveals an empirical-support gap, but the
review makes no usable empirical-support request, or the request is entirely
unactionable.

**Not applicable:** Use when the review does not request further empirical
support and the paper does not require such a request, or when the existing
empirical support is already sufficient and there is no reasonable need for an
additional request.

**Boundary note:** Whether the empirical support is theoretically necessary is
assessed under `SUB_4` or `REA_4a`; this item concerns whether the request is
concrete and actionable. The absence of a request does not automatically mean
`not_applicable`: first determine whether the paper has a reasonable empirical-
support gap.

### CON_3b

**Question:** When asking for more explanatory support, does the review specify
concrete analyses, examples, case studies, or error analyses rather than generic
additions?

**Context required:** Review text is usually sufficient; paper text helps
determine relevance.

**Definition:** When the review asks for explanatory or diagnostic support,
determine whether it specifies which analyses, examples, cases, or error
analyses should be added.

**Yes:** The review proposes a specific explanatory analysis, such as an error
analysis, case study, qualitative example, or diagnostic breakdown, and the
proposed material would explain a result, failure, mechanism, or phenomenon.

**Partial:** The review merely asks for more analysis or explanation without
specifying the type required.

**No:** The paper or the review itself reveals an explanatory gap, but the
review makes no usable explanatory-support request, or the request is not
actionable.

**Not applicable:** Use when the review does not request explanatory support and
the paper does not require such a request, or when the paper already contains
adequate diagnostic or explanatory analysis.

**Boundary note:** `CON_3b` concerns whether an explanatory request is concrete
and actionable; `REA_4b` concerns whether such analysis would help explain why
the results occur. A request for illustrative examples counts under `CON_3b`
only when the examples are intended to explain behaviour, failure, a mechanism,
or a phenomenon. If they would merely improve the writing, consider
`CLA_1/CLA_2` or `SPE_2` instead.

### IND_1

**Question:** Does the review raise independent weaknesses or risks beyond
simply echoing limitations already stated by the authors?

**Context required:** Paper text required.

**Definition:** Determine whether the review identifies its own weaknesses or
risks rather than merely repeating limitations stated by the authors.

**Yes:** The review identifies at least one specific weakness or risk that is
independent of the authors' stated limitations.

**Partial:** The review includes some independent judgement but still relies
mainly on limitations acknowledged by the authors.

**No:** The review's weaknesses largely echo the paper's own limitations and
offer little independent assessment.

**Not applicable:** Use cautiously when the review has no section on weaknesses
or risks, or when the paper contains no limitations text against which to
compare the review.

**Boundary note:** This is a top-down check for a known LLM failure mode and
requires a paper-aware judgement.

### SPE_1

**Question:** Does the review use specific references to methods, variables,
datasets, results, examples, sections, citations, or claims when making
feedback?

**Context required:** Review text is usually sufficient; paper text helps verify
accuracy.

**Definition:** Determine whether the feedback is tied to a specific method,
variable, dataset, result, example, section, citation, or claim in the paper.

**Yes:** Most key feedback identifies a specific object, allowing the reader to
understand what part of the paper the reviewer means.

**Partial:** The review identifies some specific objects, but key criticisms or
suggestions remain general.

**No:** The feedback is mostly generic—for example, “interesting”, “unclear”, or
“needs more work”—without a specific target.

**Not applicable:** Use only rarely, when the review is too short and contains
no substantive feedback.

**Boundary note:** Specificity is not the same as grounding. A specific but
incorrect reference does not automatically count as grounded under `GRO_1`.

### SPE_2

**Question:** When the review asks for clarification or revision, does it name
the missing, unclear, or problematic information precisely?

**Context required:** Review text is usually sufficient; paper text is helpful.

**Definition:** Determine whether a clarification or revision request precisely
identifies the information that is missing, unclear, or problematic.

**Yes:** The review clearly identifies what is missing, what is unclear, or what
must be revised.

**Partial:** The review makes a clarification or revision request, but phrases
it generally—for example, “clarify the method” or “provide more details”.

**No:** The review makes a clarification or revision request without identifying
its target, or the paper and review context clearly call for such a request but
the review makes none.

**Not applicable:** Use when the review makes no clarification or revision
request, the review form does not require one, and the review context provides
no reasonable need for one.

**Boundary note:** `SPE_2` concerns whether a request is precise, regardless of
whether it concerns reporting, an experiment, an analysis, or another revision.
`CON_2` concerns only whether the request relates to reporting,
reproducibility, setup, or data details.

### CLA_1

**Question:** Does the review assess readability, organisation, information
flow, or presentation in a way that would help the authors revise the paper?

**Context required:** Review text is usually sufficient; paper text is helpful.

**Definition:** Determine whether the review evaluates the paper's readability,
organisation, information flow, or presentation in a way that would help the
authors revise it.

**Yes:** The review identifies a specific problem with structure, flow, or
presentation and gives feedback that can guide revision.

**Partial:** The review states that the writing or organisation is unclear but
does not provide enough detail.

**No:** The review does not assess clarity or presentation, or provides only a
generic evaluation.

**Not applicable:** Use when the review form does not address writing or
presentation and there is no reasonably relevant presentation issue to assess.

**Boundary note:** This item does not assess whether the review itself is well
written. It assesses whether the review evaluates the clarity of the paper.

### CLA_2

**Question:** Does the review identify unclear definitions, notation,
terminology, figures, tables, or technical exposition where these affect
understanding?

**Context required:** Review text is usually sufficient; paper text is helpful.

**Definition:** Determine whether the review identifies a technical clarity
problem, such as an unclear definition, notation, term, figure, table, or
technical explanation.

**Yes:** The review identifies a specific technical exposition problem and its
effect on understanding.

**Partial:** The review states that terminology, notation, or figures are
unclear but does not locate the problem or explain its effect.

**No:** The paper has a technical clarity problem that the review does not
mention, or the review offers only surface-level copy-editing.

**Not applicable:** Use when the paper contains no relevant technical exposition
or when the review does not engage with clarity.

**Boundary note:** A surface-level typo or copy-editing comment is not sufficient
for `yes` unless it affects understanding.

### ETH_1

**Question:** Where relevant, does the review identify ethical, social, safety,
fairness, bias, privacy, data-governance, release, or environmental concerns, or
justify why none are apparent?

**Context required:** Paper text required.

**Definition:** Apply this item when the paper has relevant ethical, social,
safety, fairness, bias, privacy, data-governance, release, or environmental
stakes, or when the review form explicitly requires an ethics judgement.
Determine whether the review addresses these concerns or explains why no
apparent concern exists.

**Yes:** The review makes a specific judgement about a relevant ethics, safety,
fairness, privacy, release, or environmental issue, or reasonably explains why
no concerns are apparent.

**Partial:** The review generally mentions an ethical concern or the absence of
one without sufficient justification, or gives only a template-like judgement
despite the paper having some responsible-release relevance.

**No:** The paper clearly involves an ethics or responsible-release risk, or the
review form explicitly requires an ethics judgement, but the review does not
address it.

**Not applicable:** Use when the review form makes no request concerning ethics
and the paper has no plausible ethical, social, safety, privacy, release, or
environmental relevance.

**Boundary note:** `not_applicable` is not the same as “no concern”. The former
is the annotator's judgement that the item does not apply; the latter is a
judgement made by the reviewer and should normally be rated `yes` or `partial`
depending on the adequacy of its justification. Computational efficiency alone
does not automatically trigger `ETH_1`; the item becomes relevant only when the
review or paper connects computation to sustainability, environmental cost,
resource access, deployment risk, or other responsible-use considerations.

## Worked Boundary Examples

These examples illustrate boundaries used in the guideline pilot; they are not
extracts from the formal dataset.

### Example 1: Requesting a Non-CoT Baseline

Suppose a reviewer says that the paper should include a non-CoT baseline:

- `SUB_4`: The comment may provide evidence about the adequacy of baselines or
  comparisons because it evaluates whether the empirical support is sufficient.
- `CON_3a`: It may be a concrete empirical-support request because it specifies
  the baseline to be added.
- `COV_3`: Count it only if the comment explicitly concerns evaluation scope or
  generalisation.
- `REA_4a`: Count it only if the baseline would test whether a claim is robust.

Do not automatically assign `yes` to all four items merely because the comment
mentions a baseline.

### Example 2: Generic “Add More Experiments”

Suppose a reviewer says only “add more experiments”:

- `CON_3a`: Normally assign `partial`, because the reviewer requests empirical
  support but is not specific.
- `SUB_4`: Count the comment only if the reviewer explains why the existing
  empirical evidence is insufficient; otherwise, do not automatically assign
  `yes`.
- `REA_4a`: Count it only if the reviewer points to a robustness, ablation, or
  sensitivity test of a claim.

### Example 3: Unsupported Novelty Criticism

Suppose a reviewer says that the paper is not novel but does not identify prior
work, a baseline, a citation, or specific scholarly context:

- `SUB_1`: This may receive `partial`, because the reviewer does evaluate novelty
  or significance.
- `GRO_2`: This may receive `no` or `partial`, because the novelty judgement is
  insufficiently grounded.
- `GRO_3`: If the statement is negative criticism without evidence, it may also
  raise a concern under this item.

### Example 4: Requesting an Error Analysis

Suppose a reviewer requests an error analysis or case study to explain why a
model fails:

- `REA_4b`: Consider whether the proposed analysis would help explain why the
  results occur.
- `CON_3b`: Consider whether the request is specific and actionable.
- `SPE_2`: If the request identifies a particular type of error, case, or
  phenomenon, it may also support specificity.

### Example 5: Evaluation Dataset Versus Artifact Contribution

Suppose a method paper merely uses MNIST, GLUE, ImageNet, or another established
benchmark for evaluation:

- `SUB_3`: Normally assign `not_applicable`, because the dataset is not itself a
  paper contribution.
- `COV_2`: The comment may provide evidence if the review covers the dataset or
  evaluation setup.
- `COV_3`: The comment may provide evidence if the review discusses whether the
  tasks, datasets, or settings provide sufficient scope.
- `SUB_4`: The comment may provide evidence if the review assesses whether the
  datasets or baselines sufficiently support the contribution.

Do not treat `SUB_3` as applicable merely because the paper mentions a dataset.

### Example 6: “No Ethical Concerns”

Suppose a reviewer writes, “I do not see ethical concerns”:

- `ETH_1`: If the paper or review form calls for an ethics judgement and the
  statement has a reasonable basis, it may receive `yes`.
- `ETH_1`: If the statement is merely formulaic and the paper has some privacy,
  fairness, or release relevance, it will normally receive `partial`.
- `ETH_1`: If there is no ethics prompt and the paper has no plausible ethical,
  social, safety, privacy, or release relevance, it may be rated
  `not_applicable`.

Do not interpret `not_applicable` as the reviewer having stated that there is no
concern. `not_applicable` is the annotator's judgement about applicability.

### Example 7: Grounding Versus Unsupported Negative Criticism

Suppose a reviewer states, “the paper ignores prior work”, but identifies no
type of prior work, citation, baseline, or specific section:

- `GRO_1`: This may receive `partial` or `no`, because the review's evaluative
  judgement lacks grounding.
- `GRO_2`: If this is a novelty, related-work, or positioning judgement, consider
  whether scholarly context supports it.
- `GRO_3`: If the statement functions as negative criticism without evidence,
  it may constitute an unsupported-criticism concern.

`GRO_1` assesses general grounding; `GRO_3` is a narrower failure-mode check.

### Example 8: Requesting Hyperparameters

Suppose a reviewer writes, “Please report the learning rate, batch size, random
seeds, and train/dev/test split”:

- `CON_2`: Normally assign `yes`, because the reviewer requests specific
  reporting and reproducibility details.
- `SPE_2`: Normally assign `yes`, because the request precisely identifies the
  missing information.
- `CON_1`: The comment may also provide evidence if it functions as an
  actionable suggestion.

The same statement can support both `CON_2` and `SPE_2`, but for different
reasons: the former concerns the type of requested content, whereas the latter
concerns the precision of the wording.

### Example 9: Additional Datasets for Generalisation

Suppose a reviewer writes, “The paper only evaluates on English news data; to
support the cross-domain claim, it should test social media and biomedical
datasets”:

- `COV_3`: This may receive `yes`, because the review identifies a limitation in
  empirical scope or generalisation settings.
- `SUB_4`: This may receive `yes`, because the review explains why the existing
  evidence is insufficient to support the cross-domain claim.
- `REA_4a`: This may receive `yes` if the additional-dataset test is intended to
  test the robustness of the claim.
- `CON_3a`: This may receive `yes`, because the reviewer specifies which datasets
  or settings should be added.

One statement may support several items, but the annotator must record its
distinct role in relation to scope, adequacy, claim testing, and an actionable
request.

### Example 10: No Request Versus Not Applicable

Suppose a paper clearly lacks an important baseline and the review does not
request a baseline or any additional experiment:

- `SUB_4`: This may receive `no`, because the review does not evaluate whether
  the empirical evidence is adequate.
- `CON_3a`: This may also receive `no` if the review should reasonably have
  identified and addressed the empirical-support gap.

By contrast, if the paper already has adequate empirical support and the review
does not request further experiments:

- `CON_3a`: Normally assign `not_applicable`, because there is no reasonable
  additional empirical request to make.

Do not assign `not_applicable` whenever “the review did not request X”. First
determine whether X should reasonably have been requested.

### Example 11: Ordinary Code Availability Versus Artifact Contribution

Suppose a standard method paper merely provides implementation code in an
appendix or repository:

- `SUB_3`: Normally assign `not_applicable`, because the code is not a
  substantive artifact contribution of the paper.
- `CON_2`: This item may apply if the reviewer requests installation
  instructions, dependencies, runtime information, data-preprocessing details,
  or other information needed for reproducibility.

If the paper explicitly presents a released toolkit, benchmark suite, dataset,
model checkpoint, or reusable system as a main contribution:

- `SUB_3`: The item applies, and the review should assess the artifact's value,
  validity, usefulness, quality, or limitations.

### Example 12: Computational Efficiency and Ethics

Suppose a reviewer says only, “the method is efficient” or “training is
expensive”:

- `SUB_2` or `SUB_4`: One of these may be relevant, depending on whether the
  comment evaluates method design or empirical evidence.
- `ETH_1`: The item does not automatically apply.

If the reviewer connects computational cost to environmental impact, unequal
resource access, deployment safety, or responsible release:

- `ETH_1`: The item may apply and should receive `yes`, `partial`, or `no`
  according to the specificity and grounding of the judgement.
