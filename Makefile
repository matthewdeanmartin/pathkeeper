UV ?= uv
MAKEFLAGS += --no-print-directory

PYTHON_TARGETS := pathkeeper tests
PYLINT_MAIN_TARGETS := pathkeeper
PYLINT_TEST_TARGETS := tests
MARKDOWN_TARGETS := README.md CHANGELOG.md docs spec
YAML_TARGETS := .github mkdocs.yml .readthedocs.yaml
ABOUT_FILE := __about__.py

.PHONY: \
	sync \
	format format-python format-yaml format-markdown format-check format-check-python format-check-yaml format-check-markdown \
	lint lint-check ruff-fix ruff-check pylint pylint-tests \
	docs spell \
	security \
	test bench \
	typecheck typecheck-mypy typecheck-ty typecheck-basedpyright \
	metadata metadata-check version-check dev-status \
	check prepublish \
	run

sync:
	@$(UV) sync

format: format-python format-yaml format-markdown format-check

format-python:
	@$(UV) run isort $(PYTHON_TARGETS)
	@$(UV) run black $(PYTHON_TARGETS)
	@$(UV) run ruff check --fix --quiet $(PYTHON_TARGETS)
	@$(UV) run black $(PYTHON_TARGETS)
	@$(UV) run isort --check-only $(PYTHON_TARGETS)
	@$(UV) run black --check $(PYTHON_TARGETS)

format-yaml:
	@$(UV) run yamlfix $(YAML_TARGETS)
	@$(UV) run yamlfix --check $(YAML_TARGETS)

format-markdown:
	@$(UV) run mdformat $(MARKDOWN_TARGETS)
	@$(UV) run mdformat --check $(MARKDOWN_TARGETS)

format-check: format-check-python format-check-yaml format-check-markdown

format-check-python:
	@$(UV) run isort --check-only $(PYTHON_TARGETS)
	@$(UV) run black --check $(PYTHON_TARGETS)

format-check-yaml:
	@$(UV) run yamlfix --check $(YAML_TARGETS)

format-check-markdown:
	@$(UV) run mdformat --check $(MARKDOWN_TARGETS)

lint: ruff-fix pylint pylint-tests

lint-check: ruff-check pylint pylint-tests

ruff-fix:
	@$(UV) run ruff check --fix --quiet $(PYTHON_TARGETS)

ruff-check:
	@$(UV) run ruff check --quiet $(PYTHON_TARGETS)

pylint:
	@$(UV) run pylint --score=n --reports=n --rcfile=.pylintrc $(PYLINT_MAIN_TARGETS)

pylint-tests:
	@$(UV) run pylint --score=n --reports=n --rcfile=.pylintrc_tests $(PYLINT_TEST_TARGETS)

docs:
	@$(UV) run pylint --score=n --reports=n --rcfile=.pylintrc_docs $(PYTHON_TARGETS)

spell:
	@$(UV) run codespell --ignore-words=private_dictionary.txt pathkeeper tests README.md docs spec

security:
	@$(UV) run bandit -q -c pyproject.toml -r pathkeeper

test:
	@$(UV) run pytest -q

bench:
	@$(UV) run pytest -q -m slow tests/bench_startup.py

typecheck: typecheck-mypy

typecheck-mypy:
	@$(UV) run mypy --hide-error-context pathkeeper tests

typecheck-ty:
	@$(UV) run ty check pathkeeper tests

typecheck-basedpyright:
	@$(UV) run basedpyright

metadata:
	@$(UV) run metametameta pep621 --name pathkeeper --source pyproject.toml --output $(ABOUT_FILE)

metadata-check:
	@$(UV) run metametameta sync-check --output $(ABOUT_FILE)

version-check:
	@$(UV) run jiggle_version check

dev-status:
	@$(UV) run troml-dev-status validate .

check: format-check lint-check security test typecheck metadata-check version-check

prepublish: check dev-status

run:
	@$(UV) run pathkeeper
