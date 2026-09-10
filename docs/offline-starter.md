# First local result

This example runs the existing Holm correction helper on three synthetic
p-values. It needs Python 3.10+ and no network or third-party packages. Run the
commands from the repository root. It demonstrates a bounded helper, not agent
routing, scientific validation, or host installation compatibility.

Read the [Skill](../skills/statistical-analysis-and-multiple-testing/SKILL.md)
and its [method boundaries](../skills/statistical-analysis-and-multiple-testing/references/multiplicity-methods.md).
The example declares all three hypotheses as one complete family, Holm FWER
correction, and alpha 0.05. These are example choices, not defaults for your data.

Create a new example directory and input without overwriting existing files:

```bash
python3 - <<'PY'
from pathlib import Path
root = Path("goose-offline-example")
root.mkdir(exist_ok=False)
with (root / "pvalues.csv").open("x", encoding="utf-8") as handle:
    handle.write("record_id,p_value\ngene_a,0.01\ngene_b,0.04\ngene_c,0.20\n")
PY
```

Run the bundled helper:

```bash
python3 skills/statistical-analysis-and-multiple-testing/scripts/adjust_pvalues.py \
  --input goose-offline-example/pvalues.csv \
  --output goose-offline-example/adjusted.csv \
  --method holm --alpha 0.05
```

The command reports `completed` and writes `adjusted.csv`. Expected adjusted
values, in the original row order:

| Record | Raw p-value | Holm-adjusted p-value | Reject at 0.05 |
| --- | ---: | ---: | --- |
| gene_a | 0.01 | 0.03 | Yes |
| gene_b | 0.04 | 0.08 | No |
| gene_c | 0.20 | 0.20 | No |

Floating-point formatting may contain extra digits. Existing result paths are
refused. For another run, choose new directory and output names; keep the
original input and result for comparison.

After installing the complete Skill directory into your host's configured
skills location, the equivalent natural-language request is:

> Use statistical-analysis-and-multiple-testing on pvalues.csv. These three
> rows are one complete predeclared family. Apply Holm correction at alpha
> 0.05 and write a new adjusted.csv without overwriting anything.

Host discovery and execution still need to be checked in that host. For network
tasks, separately provide the reviewed repository connector or a compatible
host adapter as described in the [integration contract](integration-contract.md).
