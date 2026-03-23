UV ?= uv

.PHONY: sync test typecheck check run

sync:
	$(UV) sync

test:
	$(UV) run pytest

typecheck:
	$(UV) run mypy pathkeeper tests

check: test typecheck

run:
	$(UV) run pathkeeper

