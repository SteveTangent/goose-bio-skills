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

- When: The row-level entity is absent, mixed, or ambiguous.
  Ask: Does each row represent a peptide, protein group, or protein?
  Recommendation: Use one declared peptide- or protein-level boundary and route PSM or mixed-level inputs elsewhere.
- When: Blank, missing, zero, negative, or censored-value semantics are undocumented.
  Ask: What do blank, zero, negative, and censored values mean in this export?
  Recommendation: Preserve and document the producer's semantics before any recoding, normalization, or imputation decision.
- When: Sample columns, join keys, conditions, replicates, batches, or the intended contrast are unresolved.
  Ask: Which fields define the sample join, conditions, biological replicates, batches, and intended contrast?
  Recommendation: Freeze a one-to-one sample join and verify replication and confounding before downstream modeling.

## Explain and correct

Compensation / 补偿: correcting fluorescence spillover using controls. Missingness / 缺失机制: why a measurement is absent, which affects imputation.

Zeros, undetected measurements and missing values are not interchangeable. Automatic imputation or compensation can create misleading patterns.

Request assay, units/transform, control provenance and how missing or zero values were encoded.

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
