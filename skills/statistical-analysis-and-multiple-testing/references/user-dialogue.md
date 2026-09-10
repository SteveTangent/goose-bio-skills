# Focused scientific dialogue

Load when inputs are incomplete, contradictory, unfamiliar to the user, or when
explaining a consequential method choice. Reply in the user's language and adapt
detail to their experience; retain the precise scientific meaning.

## Decide what to ask

1. Separate **observed** file facts, **user-declared** study facts, and **unresolved** assumptions. Inspect supplied metadata before asking again. Do not turn a filename or value pattern into a biological fact.
2. Ask about the highest-impact unresolved decision first. Explain its consequence in one sentence, recommend a defensible route, and state exactly what small table, label or provenance record would resolve it. Closely related fields may be requested in one compact table for that decision.
3. A recommendation is not a supplied fact or approval. Wait before dependent analysis. Continue safe independent inspection. If the user does not know, offer an available provenance check or a clearly limited exploratory output; never silently fill in missing study facts.
4. If inputs are complete and compatible, act without a ritual interview. Do not require extra confirmations for unchanged authorized work. Cosmetic preferences may use a stated sensible default; choices changing the scientific result may not.

## This task's decision points

- When: Family membership is absent or incomplete.
  Ask: Which hypotheses form each complete multiplicity family?
  Recommendation: Declare the scientific family before examining adjusted results; never infer it from observed p-values.
- When: The requested error-control objective or method is unresolved.
  Ask: Should this family use ordinary BH FDR control or Holm FWER control?
  Recommendation: Use BH only when its dependence conditions fit; use Holm for FWER, and stop when arbitrary-dependence FDR control is required.
- When: Reject/not-reject decisions are requested and alpha is absent or ambiguous.
  Ask: What preregistered or protocol-specified alpha should be used?
  Recommendation: Supply the protocol value explicitly; use 0.05 only when that is the declared choice.

## Explain and correct

Experimental unit / 实验单位: the independent unit receiving a condition. Censoring / 删失: incomplete observation of event time. Multiple testing / 多重检验: simultaneous opportunities for false positives.

Non-significance does not prove no effect. A p-value is not the probability a hypothesis is true. Repeated observations require a model that respects their dependence.

Request the outcome, independent unit, group/repeated-measure structure and target effect before selecting a test.

For a suspected mistake, say what evidence raised it, why it matters, and the
smallest repair/check. Use “may indicate” for an unconfirmed inference; do not
present suspicion as certainty or silently alter data. Preserve original values
and record an agreed transformation or exclusion.

## Make progress visible

Tell the user what output answers their question. Use a small sample/assumption
table for design decisions; add a figure only when it explains a result or QC
pattern. Label units, transformations, sample counts, comparison direction and
thresholds. Distinguish observed patterns from statistical and biological claims.
Prefer exportable PNG/SVG plus underlying data for scientific figures. Do not
make a visualization or a lengthy glossary compulsory for a simple lookup.

End with the result or blocker first, linked outputs, the few decisions that
matter, and one relevant next action. A completed report must preserve partial
source analyses as partial.

## Example of the interaction

User: “Just do this analysis; use the usual settings.”
Agent: identify the concrete missing decision above, explain its effect in plain
language, and request the minimum record that resolves it. Avoid a generic list
of every possible question. If that decision was already supplied, proceed.

User provides the missing record: summarize the resolved fact briefly and act;
do not ask the same question in different words or require a final approval loop.
