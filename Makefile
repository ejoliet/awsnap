.PHONY: venv lint fmt test test-browser smoke build clean

venv:
	uv venv
	uv pip install -e ".[dev]"

lint:
	.venv/bin/ruff check src tests

fmt:
	.venv/bin/ruff format src tests

test:
	.venv/bin/pytest --cov=awsnap --cov-report=term-missing --cov-fail-under=80 -m "not browser" tests/

test-browser:
	.venv/bin/playwright install chromium
	.venv/bin/pytest -m browser tests/

smoke:
	@echo "Running smoke test (requires real AWS credentials)..."
	time .venv/bin/awsnap --verbose --out ./smoke-out

build:
	uv build

clean:
	rm -rf .venv build/ dist/ *.egg-info .pytest_cache .coverage htmlcov smoke-out/
