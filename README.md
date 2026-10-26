# Leftover

Clubs and dining halls regularly end up with extra food after events. Leftover lets them post it, and students
claim a portion and pick it up with a short code. It came out of the food-insecurity nonprofit I started.

| Student view | Host view |
|---|---|
| ![student](docs/screenshot-student.png) | ![host](docs/screenshot-host.png) |

## How it works

A host posts what they have, where it is, how many portions, and when pickup ends. A student claims one portion
and gets a 4-character code. The claim is held for 15 minutes. If they don't show up, it expires and the portion
goes back.

The tricky part is two people claiming the last portion at the same moment. Each claim runs in a transaction
that locks the listing row (`SELECT ... FOR UPDATE`), so claims on the same listing go one at a time. A partial
unique index also stops one student from holding two claims on the same listing. `tests/test_claims.py` has a test
where 30 threads go for the last 2 portions. Without the lock, more than 2 of them get one.

## Stack

FastAPI, Postgres (SQLAlchemy), Jinja templates for the main site, and a small React (Vite) dashboard on top of a
JSON API. Docker for local runs, GitHub Actions for CI. `render.yaml` deploys it to Render.

![dashboard](docs/screenshot-dashboard.png)
<sub>Dashboard with sample data.</sub>

## Running it

```bash
docker compose up --build
```

Dashboard on `localhost:3000`, site and API on `localhost:8000` (API docs at `/docs`).

Without Docker:

```bash
createdb leftover && createdb leftover_test
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # set SECRET_KEY
uvicorn app.main:app --reload --env-file .env
pytest

cd frontend && npm install && npm run dev
```

## API

| Method | Endpoint | Auth | |
|---|---|---|---|
| POST | `/api/token` | | email + password, returns a JWT (60 min) |
| GET | `/api/listings` | | food available now |
| GET | `/api/stats/daily?days=30` | | portions posted and picked up per day |
| GET | `/api/me` | JWT | current user |
| GET | `/api/me/claims` | JWT | your active claims |
| POST | `/api/listings/{id}/claim` | JWT | claim a portion, `409` if none left |

## Other notes

- Every request is logged as one JSON line (time, endpoint, status, duration). With `DD_API_KEY` set the
  lines also go to Datadog. `/health` checks the database.
- CI runs the tests against Postgres, builds the frontend and both images, starts the stack and hits it, and
  pushes the images to ghcr.io on `main`.
- Email alerts for new food are written but turned off (`EMAIL_ALERTS=on`), since sending to everyone costs
  money. When on, students with the fewest pickups that week get emailed first.
- Tables are created on startup. Changing an existing table would need Alembic.
