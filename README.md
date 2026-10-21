# Leftover: campus food rescue

A web app that matches surplus food from club events and dining halls with
students who want it.

- **Hosts** post leftover food: what it is, where, how many portions, and until when.
- **Students** see what's available, claim a portion, and get a 4-letter pickup code.
- A claim is a **hold that expires** (15 minutes by default). No-shows free the portion up for someone else.
- **Two students can never get the same last portion.** Claims lock the listing's database row, so they run one at a time (see `app/claims.py`, proven by `tests/test_claims.py::test_many_students_race_for_the_last_portion`).
- **Optional email alerts (off by default, since sending to everyone costs money):** set `EMAIL_ALERTS=on` to email students about new food, fewest-pickups-this-week first (`app/notify.py`).
- **Public impact page** at `/stats`: meals rescued, students fed, and so on.

Stack: Python (FastAPI), Postgres, server-rendered HTML. Deploys to Render's free tier.


| Student view | Host view |
|---|---|
| ![student](docs/screenshot-student.png) | ![host](docs/screenshot-host.png) |

## Quick start 

```bash
createdb leftover && createdb leftover_test
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # then edit SECRET_KEY
uvicorn app.main:app --reload --env-file .env    # http://localhost:8000
pytest
```

## Project layout

```
app/
  main.py       web pages and form handlers (the routes)
  claims.py     claiming, expiry, pickup: the concurrency-safe part
  notify.py     who gets alerted first, and sending email
  auth.py       password hashing, login checks
  models.py     database tables
  db.py         database connection
  templates/    HTML pages
  static/       CSS
tests/          pytest tests (run against real Postgres)
render.yaml     one-click deploy setup for Render
```
