# Changed-Code Coverage Gate (S2-001)

## 1. Coverage mechanism

CI measures test coverage and then checks only the lines a pull request added or changed. A pull request fails if too few of those lines are executed by tests.

- Backend: pytest-cov produces `coverage.xml`. The measurement includes every backend test, unit and integration alike.
- Frontend: Vitest (v8 provider) produces `coverage/cobertura-coverage.xml`.
- Gate: diff-cover compares the coverage report with the diff against the pull request's base branch (`origin/main`).

The gate runs only on pull requests, as a step inside the existing required jobs ("Backend tests (pytest)" and "Frontend checks (lint, test and build)"). Because it lives inside those jobs, the required status check names did not change and no branch rule update is needed.

## 2. Required threshold

At least 80% of changed, measurable lines must be covered, separately for the backend and the frontend. The value is set once in `.github/workflows/ci.yml` as `CHANGED_CODE_THRESHOLD`.

The goal is not a high overall percentage. Old code is not measured. The gate only stops new behavior from being merged with no test at all. Lines that are not executable code (comments, blank lines, type-only imports) are not counted.

## 3. What is measured and what is excluded

Backend (`Back_End/.coveragerc`):
- Measured: `app/` and `services/`.
- Excluded: `tests/`, because test files are not application code. Counting them would inflate the numbers, and a pull request that only adds tests would look like changed application code.
- Excluded: `__init__.py`, because these are package markers with no behavior.
- Excluded: `if __name__ == "__main__":` blocks (and any line marked `# pragma: no cover`). In `services/google_reviews.py` this block is a manual script for trying the review provider by hand. It is not part of the running application.
- Not excluded but known to be untested: the check in `app/db.py` that stops the app from starting when the Supabase settings are missing. It runs when the module is imported, so a test would tell us very little.

Frontend (`Front_End/clerk-nextjs/vitest.config.ts`):
- Measured: `lib/` (service layer, validation, formatting) and `components/` (React components). Component tests render the real components in jsdom, with the network layer and toast notifications replaced by test doubles.
- Excluded: test files themselves, and `lib/types.ts` (type definitions only, no runtime code).
- Excluded: `components/ui/Toast.tsx`. The component tests replace the toast system with a mock, so this file is not exercised. Changes to it need a manual review until it has its own tests.
- Not measured: the Next.js pages and routes in `app/` (the home page, the target page, the backend pass-through route) and `proxy.ts`. They are thin wrappers that hand data to the measured components, and they have no tests yet. This is a known gap, not a claim that they are tested. Add them to the `include` list in `vitest.config.ts` when tests exist.

## 4. Running it locally

Backend, from `Back_End` with the venv active:

    python -m pip install -r requirements-dev.txt
    python -m pytest --cov --cov-report=term-missing --cov-report=xml
    diff-cover coverage.xml --compare-branch=origin/main --fail-under=80

Frontend, from `Front_End/clerk-nextjs`:

    npm ci
    npm run test:coverage
    pipx run diff-cover coverage/cobertura-coverage.xml --compare-branch=origin/main --fail-under=80

Run `git fetch origin main` first so `origin/main` is current. Commit your changes before running diff-cover, or it reports on the committed difference only. The `term-missing` report and the diff-cover output both list the exact lines that are not covered, so you know what test to add.

## 5. Showing that the gate can fail

Create a branch from `main`, add a small function with real logic and no test (for example in `Back_End/services/google_reviews.py` or `Front_End/clerk-nextjs/lib/format.ts`), push it and open a pull request into `main`. The coverage step fails and the merge is blocked, because none of the new lines are covered. Add tests for the function and push again to show the step passing. Close the pull request without merging, and delete the branch.
