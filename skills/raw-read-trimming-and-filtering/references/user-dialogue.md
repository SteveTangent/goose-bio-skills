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

- When: The adapter identity, orientation, matching semantics, or use of detection remains unresolved after inspecting library metadata and declared inputs.
  Ask: Which library-supported adapter sequence and orientation, or explicitly approved detection policy, should govern this run?
  Recommendation: Use the adapter identity from library-preparation metadata and never guess a sequence; approve detection only as an explicit, recorded alternative.
- When: Any quality encoding or quality, minimum-length, N-base, or paired-filter setting required by the requested operation remains unresolved.
  Ask: Which assay- and downstream-justified quality encoding, trimming, and filtering settings should be applied?
  Recommendation: State every enabled and disabled filter explicitly and use no universal threshold; choose values justified by the assay and downstream minimum usable read length.
- When: Unique sample membership or R1/R2 pairing remains ambiguous after bounded metadata inspection.
  Ask: Which explicit sample and mate mapping should the run use?
  Recommendation: Provide one unique sample identifier and R1/R2 role for every file before processing.

## Explain and correct

Strandedness / 链特异性: how library reads relate to the transcribed strand. Coordinate convention / 坐标约定: zero- versus one-based starts and endpoint inclusion.

An empty overlap may reflect incompatible builds or coordinate conventions. Low alignment alone does not prove poor biology; inspect library/reference compatibility first.

Request the reference/build and library preparation record relevant to the suspected mismatch, not the whole sequencing archive.

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
