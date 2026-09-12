# Local qPCR input and calculation

Python >=3.10, standard library only; no installation/network inside the helper.

```text
python3 scripts/analyze_qpcr.py --self-test
python3 scripts/analyze_qpcr.py --cq cq.tsv --samples samples.tsv --assays assays.tsv --design design.json --output qpcr-new
```

TSV headers are exact:

- cq.tsv: sample_id, assay_id, run_id, technical_replicate, cq, status.
- samples.tsv: sample_id, subject_id, group.
- assays.tsv: assay_id, role, amplification_factor, cq_min, cq_max, validation_note.

All IDs are preserved as text. Sample IDs are unique and subject IDs represent
independent biological objects. Assay role is target or reference. One run_id is
supported. Each sample/assay needs 2–4 distinct technical_replicate IDs. Detected
Cq is numeric in (0,60] and must lie in that assay's declared quantitative range.
Status is detected, undetermined or missing. The last two require empty Cq, never
40 or another substituted threshold. Absent sample/assay wells block the path;
missing and undetermined records remain distinct in QC.

Amplification factors are per-cycle multipliers, not percentages: 1.9 means 90%
efficiency. Numeric factors must lie in (1,2.2], an adapter range rather than an
assay quality certification. The validation note must justify measured factors
and the valid quantitative Cq range. Use unknown when a numerical declaration or
validation note is unavailable; no calculation proceeds from unknown facts.

The exact design JSON fields:

```json
{
  "assay": "RT-qPCR",
  "method": "efficiency-corrected",
  "independent_subjects": true,
  "assay_qc_reviewed": true,
  "assay_qc_note": "User-supplied specificity, controls and range review",
  "reference_rationale": "User-supplied reference stability evidence",
  "calibrator_group": "control",
  "max_technical_cq_range": 0.5
}
```

Those notes are placeholders for supplied evidence, not default declarations.
The range threshold (0 < threshold <= 5) is a declared analysis policy, not a
universal QC rule. A group needs at least two independent subjects; 2–4 groups
are supported. DNA-qPCR/unknown assay, repeated subjects, multiple runs,
unreviewed controls, unknown references/factors, out-of-range Cq, missing wells
or excess replicate spread return needs-decision. No automatic exclusions occur.

Let m(s,a) be mean technical Cq and E(a) the validated amplification factor.
L(s,t) = -m(s,t) log2(E(t)) - mean_ref[-m(s,r) log2(E(r))].
The log2 relative result is L(s,t) minus the calibrator group's mean L(s,t).
The linear result is 2 to that power; group summaries use geometric means.
Target-specific constants cancel against the same target's calibrator. Do not
compare absolute quantities between different assays. The optional delta-delta-cq
method requires E=2 for every target/reference; otherwise choose corrected
quantification after assay validation. Equivalent factor-2 inputs give -ΔΔCq.

QC means and SD use detected wells for inspection only; if any well is unquantified,
no relative-expression files are produced. SD in the group table describes the
observed log2 subject values, not propagated efficiency uncertainty or a confidence
interval. No hypothesis test is performed, including across multiple targets.
