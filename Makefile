.PHONY: venv lint fmt test test-browser smoke build clean

venv:
	uv sync --extra dev

lint:
	uv run ruff check src tests

fmt:
	uv run ruff format src tests

test:
	uv run pytest --cov=awsnap --cov-report=term-missing --cov-fail-under=80 -m "not browser" tests/

test-browser:
	uv run playwright install chromium
	uv run pytest -m browser tests/

smoke:
	@echo "Running smoke test (requires real AWS credentials)..."
	time uv run awsnap --verbose --out ./smoke-out

build:
	uv build

clean:
	rm -rf .venv build/ dist/ *.egg-info .pytest_cache .coverage htmlcov smoke-out/
