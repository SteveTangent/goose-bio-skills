# Verification pipeline

Goose Bio Skills has two verification modes, not eight separate contributor decisions.
The existing gates remain independently runnable and retain their historical
evidence; the thin orchestrator only chooses and reports them.

```mermaid
flowchart TD
    C["change"] --> Q["quick\nverify.py quick"]
    Q --> G["generated registry check"]
    Q --> S["48-package skeleton\nall bundled self-tests"]
    Q --> V["validator self-test"]
    Q --> D["diff check"]
    G --> R{"tagged release?"}
    S --> R
    V --> R
    D --> R
    R -- "no" --> Done["ready for code review"]
    R -- "yes" --> Full["verify.py release"]
    Full --> X["connector self-test"]
    Full --> W["R1-R5 twice\nbyte-identical output"]
    X --> Seal["independent review + release evidence"]
    W --> Seal
```

## Commands

```bash
python3 scripts/verify.py quick
python3 scripts/verify.py release
```

`quick` is the normal local and pull-request path. It still validates every
package because the full skeleton currently takes only a few seconds and avoids
fragile change detection. `release` adds the connector and two fresh runs of
each retained Wave runner. Full release evidence, CodeGraph refresh, and
independent review remain release activities rather than per-edit gates.

Historical Wave runners are frozen evidence executors. New work should not copy
their hashing, JSON, or subprocess helpers into another Wave runner unless a
new retained evidence boundary genuinely requires it.

The current [source-code graph](codegraph.md) records implementation structure,
not scientific or routing assurance.
