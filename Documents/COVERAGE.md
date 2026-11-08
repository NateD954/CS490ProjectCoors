# Changed-Code Coverage Gate (S2-001)

## 1. Coverage mechanism

CI measures test coverage and then checks only the lines a pull request added or changed. A pull request fails if too few of those lines are executed by tests.

- Backend: pytest-cov produces `coverage.xml`.
- Frontend: Vitest (v8 provider) produces `coverage/cobertura-coverage.xml`.
- Gate: diff-cover compares the coverage report with the diff against the pull request's base branch (`origin/main`).

The gate runs only on pull requests, as a step inside the existing required jobs ("Backend tests (pytest)" and "Frontend checks (lint, test and build)"). Because it lives inside those jobs, the required status check names did not change and no branch rule update is needed.

## 2. Required threshold

At least 80% of changed, measurable lines must be covered, separately for the backend and the frontend. The value is set once in `.github/workflows/ci.yml` as `CHANGED_CODE_THRESHOLD`.

The goal is not a high overall percentage. Old code is not measured. The gate only stops new behavior from being merged with no test at all. Lines that are not executable code (comments, blank lines, imports of types) are not counted.

## 3. Exclusions and why

Backend (`Back_End/.coveragerc`):
- `tests/`: test files are not application code.
- `__init__.py`: package markers with no behavior.

Frontend (`Front_End/clerk-nextjs/vitest.config.ts`):
- Only `lib/` is measured (the service layer, validation and formatting). React components, pages and the proxy route are not measured yet, because the project has no component test setup. This is a known gap, not a claim that those files are tested. When component tests are added, widen the `include` list.
- `lib/**/*.test.ts` and `lib/types.ts`: tests, and a file with only type definitions.

## 4. Running it locally

Backend, from `Back_End` with the venv active:

    python -m pip install -r requirements-dev.txt
    python -m pytest --cov --cov-report=term-missing --cov-report=xml
    diff-cover coverage.xml --compare-branch=origin/main --fail-under=80

Frontend, from `Front_End/clerk-nextjs`:

    npm ci
    npm run test:coverage
    pipx run diff-cover coverage/cobertura-coverage.xml --compare-branch=origin/main --fail-under=80

Run `git fetch origin main` first so `origin/main` is current. Commit your changes before running diff-cover, or it reports on the committed difference only. The gate reports which changed lines are not covered, so you know what test to add.

## Showing that the gate can fail

Create a branch, add a small function with real logic and no test (for example in `lib/format.ts` or `app/main.py`), push it and open a pull request into `main`. The coverage step should fail and block the merge. Close the pull request without merging.
