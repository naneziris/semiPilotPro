# ADR entries and changelog lines

## ADR (`docs/decisions.md`) — newest first, at the top of *Entries*

```markdown
### ADR-<NNN>: <decision in one line>
- **Date:** YYYY-MM-DD
- **Status:** accepted            # or: superseded by ADR-<NNN>
- **Context:** 1–2 sentences — the forces at play
- **Decision:** 1 sentence
- **Rejected alternatives:**
  - <alternative> — <one-sentence reason>
- **Consequences:** 1–2 sentences — what this makes easier, and what it makes harder
```

`<NNN>` is the next number after the highest existing one. Superseding an older ADR: add the new one and change the
old one's status line only.

## Changelog (`docs/CHANGELOG.md`) — Keep a Changelog style

```markdown
## [Unreleased]
### Added
- Shop admins can export the orders list as CSV, with the list's filters applied (up to 10 000 rows).
### Changed
### Fixed
### Deprecated
### Removed
```

One line per user-visible change, written for a user of the product — not "refactored `listOrders`", but what
someone using the product can now do differently. Internal-only changes get no line.
