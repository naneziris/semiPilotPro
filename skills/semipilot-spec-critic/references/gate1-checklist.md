# Gate 1 checklist

Work through all seven. A spec fails Gate 1 if any item fails; report all failures in one verdict so the refiner
fixes them in one round.

## 1. Observable, tagged criteria
- Every criterion under *Acceptance Criteria* describes an outcome someone could observe (UI text, return value,
  file content, HTTP status, persisted row) — not a quality ("robust", "clean", "fast").
- Every criterion ends with exactly one `[check: <ref>]`.
- Each ref is either a test name / unique substring in the repository's naming style, or `lint` / `typecheck` /
  `build`, and a test with that name could actually assert the criterion as written.
- **Reject when:** a criterion is untagged, tagged with something no check could prove, or bundles two behaviours.

## 2. Coverage
- Every bullet of *In Scope* is covered by at least one criterion.
- No criterion goes beyond *Problem* / *In Scope* (silent scope creep).
- **Reject when:** an in-scope item has no criterion, or a criterion adds unrequested behaviour.

## 3. Feasibility vs. data model and architecture
- No criterion needs data the current schema/types cannot represent.
- No criterion contradicts a documented invariant, ADR (`docs/decisions.md`), dependency rule
  (`docs/dependencies.md`) or a contract the spec lists under "must not change".
- **Reject with a citation:** the card line, ADR number, type or file.

## 4. The impact analysis is real
- Modules/cards named actually own the behaviour (verify in the cards' `code:` paths or the code).
- Risk levels are justified; listed tests exist.
- With a knowledge layer, the confirmed tags resolve to the cards the analysis names.
- **Reject when:** the analysis names the wrong owner, misses an obvious consumer, or cites tests that do not exist.

## 5. Edge cases
- Empty / null input, authorization, concurrency, and the failure modes of each external dependency the idea
  implies are either covered by a criterion or explicitly *Out of Scope*.
- **Reject when:** an implied edge case is silently missing — the unattended loop will guess.

## 6. Open questions
- Each has a recommended default.
- None of them, answered either way, would silently change a public interface (those must be decided now).

## 7. Size
- Plausibly ≤ 8 tasks of ≤ 5 files each.
- **Reject when larger**, with a proposed first slice ("Slice 1: criteria 1–4; move 5–9 to a second requirements file").

## Not reasons to reject
Wording preferences, formatting, a different but equally valid scope split, or anything the planner can decide
(names, files, algorithms). Put those in *Notes for the reviewer* if they matter.
