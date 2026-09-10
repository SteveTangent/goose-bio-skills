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

- When: Duplicate identifiers are present and the collapse policy is absent or ambiguous.
  Ask: How should duplicate identifiers be collapsed?
  Recommendation: Use one deterministic rule declared before enrichment.
- When: Tied ranking statistics are present and the tie policy is absent or ambiguous.
  Ask: How should tied ranking statistics be ordered?
  Recommendation: Use a deterministic tie policy and report tie prevalence.
- When: The gene-set permutation count or random seed is absent or ambiguous.
  Ask: Which gene-set permutation count and random seed should the preranked run use?
  Recommendation: Use gene-set permutations with a recorded seed; phenotype permutation requires a separate expression-matrix and sample-label contract.

## Explain and correct

ORA / 过度代表分析: selected-list overlap against eligible background. GSEA / 排序基因集富集: concentration toward ends of a complete signed ranking. FDR / 假发现率: a multiple-testing error concept.

Do not default to the whole genome for ORA or feed only significant genes to GSEA. Enrichment does not prove pathway activation. GSEA empirical FDR and BH-adjusted p-values are different estimates.

Request taxon, identifier namespace, collection release and either the eligible ORA universe or complete ranking metric/direction.

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
