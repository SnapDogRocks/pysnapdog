# Contributing

Thanks for helping. The library is small on purpose, so most changes are quick to review.

## Setup

The project uses [uv](https://docs.astral.sh/uv/) and Python 3.14.

```bash
uv sync
uv run lefthook install      # local hooks; needs gitleaks (brew install gitleaks)
```

## Checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --cov          # coverage floor 95 %
```

CI runs the same and `uv audit`. The hooks run a subset: `pre-commit` stays under three seconds,
`pre-push` runs mypy and the tests. If a hook is in your way, tell us in the pull request instead
of reaching for `--no-verify`.

## Commit messages: Conventional Commits

Every pull request title follows [Conventional Commits](https://www.conventionalcommits.org/):

```text
<type>(<scope>): <description>
```

- `scope` is optional, lower case.
- Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`,
  `revert`.
- A breaking change is marked with `!` after the type or a `BREAKING CHANGE:` footer.

Pull requests are squash-merged, so the **title** becomes the commit on `main`, and
release-please reads it to pick the next version and the changelog entry. Commit messages,
pull request texts and branch names are written in English.

One pull request carries one kind of change. A fix that travels with a `feat` is filed under
Features in the changelog, where nobody looks for it.

## Branches

`type/short-description`, with the same types as above, for example `feat/zone-control`.

## Tests

The tests run against a fake server (`tests/conftest.py`) whose answers follow the server's
`openapi.json`. When you add an endpoint, add the fake route, a model if the response needs one,
and a test for the success path and for each way it can fail.

## License

By contributing you agree that your work is licensed under the [Apache License 2.0](LICENSE).
