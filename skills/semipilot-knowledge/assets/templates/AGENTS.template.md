# {{REPO_NAME}} — instructions for coding agents

<!-- TEMPLATE NOTES (delete this comment when filled): keep this file ≤ 80 lines. Every agent loads it on every
     request (GitHub Copilot, Claude Code, Codex, Cursor, …); it is a router and a rulebook, not documentation.
     Depth belongs in docs/cards/ and .github/instructions/. Replace every {{TODO}} — semipilot doctor and the
     plan critic treat a file with {{TODO}} markers as empty. Update it whenever an agent makes the same mistake
     twice. -->

{{TODO: 2–4 sentences — what this product/service is, the stack, where it runs.}}

## Commands

- Build: {{BUILD}}
- Test: {{TEST}}
- Lint: {{LINT}}

## Conventions

- {{TODO: language / framework versions}}
- {{TODO: naming — files, functions, tests (cite an example file)}}
- {{TODO: patterns to follow; patterns that are deprecated here}}
- All tests pass before a change is done; never skip, weaken or delete a failing test.

## Architecture

- {{TODO: module structure in five lines — where things live, what may import what}}
- {{TODO: data flow — request → … → persistence}}

## Invariants

{{TODO: the rules that have caused or prevented a real bug in THIS repository. Numbered. Concrete ("bump X when Y
changes"), never aspirational. Source them from bug history, not imagination. "None identified yet" is fine.}}

## Cross-cutting triggers

{{TODO: every "if you change X, you must also do Y" pair, e.g. "persisted-schema change → version bump + migration".
"None identified yet — add them as they bite" is fine.}}

## Things agents get wrong here

- {{TODO: add the first correction the first time it happens, or delete this line}}
