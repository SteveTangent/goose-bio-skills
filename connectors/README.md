# Research connectors

This directory is the optional, repository-level configuration boundary for
reviewed external research services. It is not an additional Skill and is not
required by any offline core.

The current connector mode is **plan-only**. The doctor never imports a network
client, opens a socket, calls a provider, submits a job, downloads a file, or
charges a quota. Live provider adapters remain separate future work.

## Files

- `providers.json` is the exact provider-ID and host allowlist. It records the
  purpose, fields that would leave the machine, credential shape, billing or
  access boundary, and official documentation for each reviewed provider.
- `example.config.json` shows user configuration. Copy it outside the repository
  and keep only the providers you intend to use.
- `../scripts/check_research_connectors.py` is the single placeholder and doctor
  for all Skills.

Skill manifests use:

- `network_mode`: exactly `none`, `optional`, or `required`;
- `external_services`: only canonical IDs present in `providers.json`.

An unspecified hosted service, object store, cloud environment, or arbitrary URL
must not be assigned a guessed provider ID.

## User configuration

User configuration contains only provider enablement and **environment-variable
names**. It never contains an email address, token, API key, password, endpoint,
query, accession, sequence, gene list, molecule, or other research data.

```json
{
  "schema_version": "0.1.0",
  "providers": {
    "openalex": {
      "enabled": true,
      "credential_env": {
        "api_key": "BIO02_OPENALEX_API_KEY"
      }
    }
  }
}
```

Environment-variable names must use the dedicated `BIO02_` prefix followed by
uppercase ASCII letters, digits, and underscores. Secret values remain in the
user's environment or secret manager. The doctor reports only whether a
credential mapping is configured and available; it prints neither the variable
name nor its value.

## Two-stage disclosure and confirmation

Stage 1 names the provider but does not provide a config path:

```text
python3 scripts/check_research_connectors.py --provider openalex
```

The doctor emits the complete disclosure followed by
`status: needs-user-confirmation` and a deterministic `confirmation_token`. It
does not inspect a user configuration or credential environment variable.

After reviewing that disclosure, stage 2 repeats the same provider selection and
supplies the exact token:

```text
python3 scripts/check_research_connectors.py \
  --provider openalex \
  --config /path/to/research-connectors.json \
  --acknowledge bio02-ack-v1-<exact-token-from-stage-1>
```

The same handshake works across the complete allowlist:

```text
python3 scripts/check_research_connectors.py \
  --all \
  --config /path/to/research-connectors.json \
  --acknowledge bio02-ack-v1-<exact-token-for-the-all-disclosure>
```

Output is JSON Lines. For every requested provider, the first event is always a
`disclosure` containing:

- canonical provider ID and allowed hosts;
- purpose;
- `would_send` fields;
- credential requirements;
- billing, quota, or terms boundary;
- plan output (`stdout-jsonl`) and remote output (`none`);
- `network_performed: false`.

If `--acknowledge` is absent or differs by even one character, the doctor returns
`needs-user-confirmation` without opening, parsing, checking the existence of, or
otherwise touching the supplied config path. Only an exact acknowledgement lets
it read configuration and emit provider `plan` events plus one `summary` event.

After acknowledgement, missing configuration is `needs-user-config`; a
configured but unset required environment variable is `needs-credential`.
Successful validation is `config-validated`, never `live-ready`. Every event
keeps `network_performed: false`, `live_ready: false`, and
`paid_use_authorized: false`; providers whose paid tier exists continue to state
that separate paid authorization is required.

Exit codes:

- `0`: every requested provider configuration is `config-validated`;
- `2`: user configuration is missing, disabled, or incomplete;
- `3`: catalog, argument, or configuration validation failed;
- `4`: required environment variables are named but not set.
- `5`: disclosure has not received the exact confirmation token.

Unknown provider IDs, arbitrary hosts, direct credential values, and extra
configuration fields fail closed.

## Deterministic check

```text
python3 scripts/check_research_connectors.py --self-test
```

The self-test validates the frozen provider allowlist, deterministic token,
disclosure order, environment-name-only configuration, fail-closed unknown
providers, missing configuration status, and zero-network plan output. A
malicious config-loader probe and an mtime assertion prove that absent or wrong
acknowledgement cannot touch the supplied config file.
