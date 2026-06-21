# Langfuse Observability Plugin

This plugin ships bundled with Prostor but is **opt-in** — it only loads when
you explicitly enable it.

## Enable

Pick one:

```bash
# Interactive: walks you through credentials + SDK install + enable
prostor tools  # → Langfuse Observability

# Manual
pip install langfuse
prostor plugins enable observability/langfuse
```

## Required credentials

Set these in `~/.prostor/.env` (or via `prostor tools`):

```bash
PROSTOR_LANGFUSE_PUBLIC_KEY=pk-lf-...
PROSTOR_LANGFUSE_SECRET_KEY=sk-lf-...
PROSTOR_LANGFUSE_BASE_URL=https://cloud.langfuse.com   # or your self-hosted URL
```

Without the SDK or credentials the hooks no-op silently — the plugin fails
open.

## Verify

```bash
prostor plugins list                 # observability/langfuse should show "enabled"
prostor chat -q "hello"              # then check Langfuse for a "Prostor turn" trace
```

## Optional tuning

```bash
PROSTOR_LANGFUSE_ENV=production       # environment tag
PROSTOR_LANGFUSE_RELEASE=v1.0.0       # release tag
PROSTOR_LANGFUSE_SAMPLE_RATE=0.5      # sample 50% of traces
PROSTOR_LANGFUSE_MAX_CHARS=12000      # max chars per field (default: 12000)
PROSTOR_LANGFUSE_DEBUG=true           # verbose plugin logging
```

## Disable

```bash
prostor plugins disable observability/langfuse
```
