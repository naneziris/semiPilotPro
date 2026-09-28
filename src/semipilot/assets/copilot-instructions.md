# {{REPO_NAME}} — instructions for Copilot

Keep this to about one page. It is the shared memory every agent (interactive and unattended) reads first.
Update it whenever Copilot makes the same mistake twice.

## Commands

- Build: {{BUILD}}
- Test: {{TEST}}
- Lint: {{LINT}}

## Conventions

- <language / framework versions>
- <naming: files, functions, tests>
- <patterns to follow; patterns that are deprecated here>
- All tests pass before a change is done; never skip, weaken or delete a failing test.

## Architecture

- <module structure in five lines: where things live, what may import what>
- <data flow: request → … → persistence>

## Things Copilot gets wrong here

- <add the first correction the first time it happens>
