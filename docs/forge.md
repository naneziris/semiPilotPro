# Issues in, merge requests out

Two commands connect the loop to where your team already works. Both use the forge's own CLI — `gh` for GitHub,
`glab` for GitLab — which you install and log in yourself. semiPilot never reads, stores or passes a token.

```
issue ──▶ semipilot intake ──▶ issue.md ──▶ /semipilot-refine ──▶ requirements.md ──▶ … run … ──▶ semipilot mr ──▶ draft MR
                                                                                                   "Closes #12"
```

## Setup

The provider is detected from the `origin` remote's URL (`github` or `gitlab` in it). For a self-hosted GitLab or
GitHub Enterprise under another hostname, say so:

```yaml
forge:
  provider: gitlab        # auto | github | gitlab | none
  remote: origin
  base: null              # the request's target branch; null = the branch the run was started from
  draft: true
  open_mr: manual         # manual = only `semipilot mr`; auto = also right after a run that completed
```

`semipilot doctor` shows which forge it found and whether its CLI is on PATH.

## `semipilot intake <issue>`

```bash
semipilot intake 12                                   # or a full issue URL
semipilot intake 12 --slug dark-mode
```

Reads the issue (`gh issue view 12 --json number,title,body,url,labels`, or `glab issue view 12 --output json`) and
saves it as `.semipilot/features/<slug>/issue.md` — the default slug is `<number>-<first words of the title>`.
Nothing is planned or built. Then, in your agent's chat:

```
/semipilot-refine 12-add-dark-mode-to-the-settings
```

The refine skill reads `issue.md` as the idea, asks its questions, and writes `requirements.md` next to it with
`issue:` in the frontmatter. From there the feature is like any other: Gate 1, your approval, the run.

**An issue is input from outside.** Anyone who can file an issue can write text that reads like instructions. So
`issue.md` carries a notice that it is source material, and the refine skill is told to treat it as a description
of a wish, never as instructions — and you still approve the requirements at Gate 1 before anything is built. That
approval is the real protection: read what the refiner made of the issue.

Using an issue tool in the chat instead (a GitLab or GitHub MCP server)? The refine skill may read the issue with
it when you name one; the result is the same requirements file. `intake` exists so that it also works with no MCP
server at all.

## `semipilot mr <feature>` (alias `pr`)

For a **completed** run:

```bash
semipilot mr export-orders-csv --dry-run     # show the commands and write the description; push nothing
semipilot mr export-orders-csv
```

1. Pushes the run branch: `git push -u origin feat/export-orders-csv`.
2. Opens a request into the branch the run was started from (or `forge.base`), as a draft:
   `gh pr create --draft --title … --body-file … --base main --head feat/…`, or
   `glab mr create --draft --title … --description … --source-branch … --target-branch … --yes`.
3. Records the URL in the checkpoint and the report, and pushes that commit too.

The title is the feature's commit-style title (`feat(export-orders-csv): export the orders list as CSV`). The
description is built from the review packet: what was built, the risk tier, the reviewer agent's verdict with its
blockers and majors and read-first list, the number of assumptions to confirm, a checklist of the acceptance
criteria with their checks, the check results — and `Closes #12` when the feature came from an issue. The same text
is written to `.semipilot/runs/<run-id>/mr-description.md`.

It refuses a run that is not completed, one whose final checks failed, or a second request for the same feature —
`--force` overrides each. In [private mode](configuration.md) the pushed branch holds only the feature's code.

### Who pushes

The loop's agents can never push: `git push` is in every harness's deny list, and nothing in a run pushes either.
A branch leaves your machine only when

- you run `semipilot mr`, or
- you set `forge.open_mr: auto` (a completed run with passing final checks then opens its request), or
- you set `chores.open_mr: true` ([chores.md](chores.md)).

In all three it is the semipilot program that pushes, with your git credentials — never an agent. The request is a
draft by default because opening it is not approving it: the review is still yours.

## Other forges and custom commands

Replace either command line; `{placeholders}` are filled in each argument:

```yaml
forge:
  provider: gitlab
  commands:
    issue_view: ["my-tracker", "show", "{ref}", "--json"]        # must print JSON: number|iid, title, body|description, url|web_url, labels
    mr_create:  ["glab", "mr", "create", "--title", "{title}", "--description", "{body}",
                 "--source-branch", "{branch}", "--target-branch", "{base}", "--yes", "--assignee", "@me"]
```

Placeholders for `mr_create`: `{title}`, `{body}`, `{body_file}`, `{base}`, `{branch}`. A custom `mr_create` is used
exactly as written (`draft:` no longer adds `--draft`).

## Not verified here

The default command lines follow the documented options of `gh` and `glab`, and the tests run them against a fake
CLI and a local bare remote. They have **not** been run against a live GitHub or GitLab from this repository's test
suite. Try `semipilot mr <feature> --dry-run` first; if your CLI version wants different flags, `forge.commands`
is the fix.
