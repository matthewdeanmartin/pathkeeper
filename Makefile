UV ?= uv

.PHONY: sync test typecheck check run

sync:
	$(UV) sync --python 3.14

test:
	$(UV) run pytest

typecheck:
	$(UV) run mypy pathkeeper tests

check: test typecheck

run:
	$(UV) run pathkeeper

