"""AI creation wizard (AI_WIZARD_PLAN Phase 8).

The one rule that governs everything here: **the model proposes, code
disposes.** Nothing in this package mutates a wedding; providers return
schema-validated objects that the pipeline stores on an AiJob for a human to
review and apply.

Layout:
  types.py      — the one-method text-model port (TextModel protocol)
  prompts.py    — prompt registry: code defaults + ai_prompts DB overrides
  pricing.py    — per-(provider, model) price table → money at write time
  ledger.py     — append-only AiUsageLedger writer
  providers/    — adapters: anthropic (reference), fake (offline/tests)
"""
