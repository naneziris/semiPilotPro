# PilotInLoop autonomous loop — entry points. Run from the repository root.
PY ?= python3
ORCH := $(PY) .github/pilotinloop/orchestrator.py

.PHONY: preflight pilotinloop resume rollback report validate-plan test-pilotinloop

preflight:        ## make preflight FEATURE=<slug>   — questions-only planner, criteria + health + auth checks
	$(ORCH) preflight $(FEATURE)

pilotinloop:        ## make pilotinloop FEATURE=<slug>   — start the autonomous run (nohup it: see README)
	$(ORCH) pilotinloop $(FEATURE)

resume:           ## continue from the first non-done task
	$(ORCH) resume

rollback:         ## make rollback TASK=T3 — revert a task and its dependents, set them back to pending
	$(ORCH) rollback $(TASK)

report:           ## regenerate the morning report from the checkpoint
	$(ORCH) report

validate-plan:    ## make validate-plan PLAN=path/to/plan.json
	$(ORCH) validate-plan $(PLAN)

test-pilotinloop:   ## run the orchestrator's own test suite (uses a fake Copilot CLI)
	cd .github/pilotinloop && $(PY) -m pytest tests -q
