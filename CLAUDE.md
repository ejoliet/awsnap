# awsnap

## Python tooling: uv only

Use `uv` for everything Python here — never bare `pip`, `python -m venv`, or `.venv/bin/<tool>`.

| Task | Command |
|------|---------|
| Create env + install | `uv sync --extra dev` (or `make venv`) |
| Run tests | `uv run pytest ...` (or `make test`) |
| Lint / format | `uv run ruff check src tests` / `uv run ruff format src tests` |
| Run the CLI | `uv run awsnap --out ./out` |
| Add a dependency | `uv add <pkg>` (`uv add --optional dev <pkg>` for dev extras) |
| One-off tool | `uvx <tool>` |
| Build wheel/sdist | `uv build` |

`bootstrap.sh` also uses uv: it installs uv via the standalone installer when missing
(AWS CloudShell has none), then runs `uvx --from git+... awsnap`. uv supplies its own
Python, so nothing lands in system or user site-packages.

## Spec

`RDD.md` is the source of truth for scope and behavior; `spike/gate0.md` holds the Gate-0 kill criteria.
