# ReviewLens (CS490 Project Coors)

ReviewLens collects Google Maps reviews for a business so they can be analyzed.

* Backend: Back\_End/ (FastAPI), runs on port 8000
* Frontend: Front\_End/clerk-nextjs/ (Next.js), runs on port 3000

## Requirements

* Git
* Node.js 22 or newer
* Python 3.11

Commands below are for Windows PowerShell.

## Get the code

&#x20;   git clone https://github.com/NateD954/CS490ProjectCoors CS490ProjectCoors
    cd CS490ProjectCoors
    git checkout main
    git pull


## Keys you need

The .env files are not in git. Ask a teammate for the Supabase URL and secret key, the Clerk publishable and secret keys, and the OpenWeb Ninja API key.

If you are using a new Supabase project, run Database/schema.sql in the Supabase SQL editor to create the tables.

## Run the backend

&#x20;   cd Back\_End
    python -m venv .venv
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    .\\.venv\\Scripts\\Activate.ps1
    python -m pip install -r requirements-dev.txt


Create a Root .env with these values:

&#x20;   SUPABASE\_URL=
    SUPABASE\_SECRET\_KEY=
    CLERK\_SECRET\_KEY=
    NEXT\_PUBLIC\_CLERK\_PUBLISHABLE\_KEY=
    X-API-Key=


Start the server:

&#x20;   python -m uvicorn app.main:app --reload --port 8000


## Run the frontend

In a second PowerShell window:

&#x20;   cd Front\_End\\clerk-nextjs
    npm ci


Create Front\_End\\clerk-nextjs.env.local with these values:

&#x20;   NEXT\_PUBLIC\_CLERK\_PUBLISHABLE\_KEY=
    CLERK\_SECRET\_KEY=
    BACKEND\_URL=http://localhost:8000


Start the dev server:

&#x20;   npm run dev


Open http://localhost:3000, sign in, and go to /home. Create a target with the business name and the full Google Maps URL (it must contain a place id like 0x...:0x...), then open it and click Start ingestion.

## Run the tests

Backend, from Back\_End with the venv active:

&#x20;   python -m pytest -v


Frontend, from Front\_End\\clerk-nextjs:

&#x20;   npm test
    npm run build


Use python -m pytest instead of plain pytest so the app and services folders are found. The backend tests do not contact any real services, but app/db.py needs the Supabase variables set when it loads, so keep your .env in place.

## Common problems

* Scripts are disabled: run the Set-ExecutionPolicy line again in the current window.
* No module named pytest: you are not in Back\_End or the venv is not active.
* SUPABASE\_URL is not set: .env is missing or in the wrong folder.
* Backend server could not be reached: the backend is not running, or BACKEND\_URL is wrong.
* 401 on every request: the Clerk keys do not match, or you are signed out.
* Ingestion returns 502: the reviews API key is wrong, or the Maps URL has no place id.
* ERESOLVE during npm install: use npm ci instead.

