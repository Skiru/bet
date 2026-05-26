---
name: bet-formatting-artifacts
description: "Activation guidance for betting artifact formatting — points to the canonical instruction file and explains when to load it."
user-invokable: false
---

# Formatting Betting Artifacts

Use this skill when you need a quick activation reminder for betting outputs. The canonical rules live in [betting-artifacts.instructions.md](../../instructions/betting-artifacts.instructions.md).

## Load When

- writing coupons, reports, ledgers, or settlement notes
- checking that artifact names, IDs, or timestamps match the active betting-day convention
- reminding a downstream prompt that the formatting instruction is the source of truth

## What This Skill Adds

- a short activation cue before formatting work
- a pointer to the canonical instruction file
- a reminder to pair formatting with `bet-building-coupons` or `bet-settling-results` when the task needs construction or settlement context

## What It Does Not Add

- full CSV schemas
- translation tables
- versioning rules
- section-order templates
- duplicate artifact policy

## Operating Rule

Keep the skill concise. If you need the actual formatting rule, load the instruction file instead of expanding this skill.
