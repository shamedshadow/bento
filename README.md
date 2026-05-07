# Bento

Self-hosted, multi-user food tracker. Per-user primary metric calibration (calories, net carbs, total carbs, or protein) — one codebase serves users with different tracking needs without making either feel secondary.

Sibling to Tender on the homelab. FastAPI + HTMX + Alpine.js + SQLite + SQLAlchemy + Alembic, deployed via Docker Compose.

## Design principles

- **Low-friction logging.** Recents, favorites, and saved meals are first-class. Two-tap re-log target.
- **No shame mechanics.** Targets are soft reference lines, not verdicts. Descriptive language only.
- **No medical decision support.** Tracks data; never recommends doses, foods, or macro goals.
- **Net carbs are computed at display time** (`carbs - fiber`), never stored.
- **Multi-user from the first migration.** Magic link + PIN auth, no email service required.

## Run it

```bash
docker compose up -d --build
```

Then visit `http://<host>:8081`. On first launch you'll be prompted to create the admin account.

## Local development

```bash
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

App is at `http://127.0.0.1:8000`.

## Environment variables

| Var | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/bento.db` | SQLAlchemy async URL |
| `PHOTOS_DIR` | `./data/photos` | Where meal photos are stored |
| `BENTO_COOKIE_SECURE` | `false` | Set `true` when serving over HTTPS |
| `BENTO_SESSION_SECRET` | _(generated)_ | Session secret; auto-generated and persisted on first run if unset |

## First admin

On first launch the app redirects all routes to `/setup`. Fill in name, email, primary metric, daily target, and a 4–6 digit PIN. After that, `/setup` is no longer reachable and the admin can provision more users via `/admin/users`.

## Adding a second user

1. Sign in as admin → **Admin → Users → Create user**.
2. Fill in name, email, primary metric, and daily target.
3. Copy the magic link the form returns. **Text it to the user** — Bento doesn't send email.
4. The user opens the link, picks a PIN, and is logged in.

If a user loses their magic link before setting a PIN, the admin can regenerate it from the same page. Magic links expire 7 days after creation.

## Backup

The entire app state lives under `data/`:

- `data/bento.db` — SQLite database
- `data/photos/{user_id}/{entry_id}.jpg` — meal photos

Stop the container, `cp -r data/ data-backup-$(date +%F)/`, restart. That's the whole backup story.

## Data ownership

Each user can export their entries to CSV from **Settings → Export data**. Take your data and go anytime.
