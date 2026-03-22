# EMERGING-LABS

Datacenter inspection and telemetry platform built with FastAPI, PostgreSQL, and Kafka-compatible streaming.

## What This Project Does

This project combines:

- role-based user access (admin/user/supervisor/reviewer/manager)
- equipment, place, role, and user management
- daily inspection workflow with multi-stage approvals
- live telemetry ingestion, anomaly detection, alerting, and dashboard updates

## Core Features

- Authentication with JWT cookie-based login/logout
- Role-based authorization guards across protected routes
- Equipment CRUD with latest metadata snapshots (temperature, voltage, pressure, frequency)
- Place/Role/User admin pages
- Daily Inspection (DI) submission and approval lifecycle
- Telemetry pipeline with:
  - random telemetry producer every 5 seconds
  - one topic and two independent subscribers
  - DB persistence + live dashboard feed
- Active telemetry alerts for anomalous readings

## High-Level Architecture

### Application Layer

- `app/main.py`: app bootstrap, router wiring, startup initialization
- `app/routes/`: HTTP routes and page/API handlers
- `app/core/`: auth guards, telemetry hub, bootstrap utilities
- `app/models/`: SQLAlchemy ORM entities
- `app/templates/`: Jinja2 UI templates

### Data + Streaming Layer

- Postgres (`db`) stores users, DI records, equipment metadata, telemetry records, alerts
- Kafka-compatible broker (`kafka` via Redpanda) handles telemetry topic fan-out
- Telemetry producer publishes random readings to `telemetry.raw`
- Consumer 1 (`telemetry-db-consumer`) writes telemetry events to DB
- Consumer 2 (`telemetry-app-consumer`) forwards events to app live endpoint

## Service Topology (Docker Compose)

- `app` -> FastAPI web app (`http://localhost:8000`)
- `db` -> Postgres (`localhost:5433` mapped to container `5432`)
- `kafka` -> Redpanda broker (internal `kafka:9092`, external `localhost:19092`)
- `telemetry-publisher` -> random telemetry producer (5-second interval)
- `telemetry-db-consumer` -> DB subscriber group: `telemetry-db-writer`
- `telemetry-app-consumer` -> live-app subscriber group: `telemetry-app-updater`

## Telemetry Flow

1. `telemetry-publisher` fetches active components from `/api/telemetry/components`
2. Publisher generates random metrics and pushes to topic `telemetry.raw`
3. `telemetry-db-consumer` consumes same topic, writes `telemetry_records`, updates `telemetry_alerts`
4. `telemetry-app-consumer` consumes same topic, posts to `/api/telemetry/live`
5. Dashboard polls `/api/telemetry/dashboard` every 5 seconds and updates cards

This is the requested “2 subscribers for 1 topic” pattern.

## Inspection Workflow

Two inspection route groups exist in code:

- `/di/...` (daily inspection dashboard/form/list/workflow endpoints)
- `/inspection/...` (inspection cards, approval, status, snapshots)

Core status flow:

- `submitted` -> `supervisor_approved` -> `reviewer_approved` -> `completed`

Roles allowed to approve each stage are enforced in route logic.

## Startup Bootstrap Behavior

On app startup (`app/main.py`):

- creates tables via `Base.metadata.create_all`
- seeds default auth roles/user if missing
- seeds default telemetry demo entities if missing

Default seeded user:

- username: `admin`
- password: `admin123`

Default seeded demo equipment:

- `Battery Bank A`
- `Server Rack A`

## Run The Project

From project root (`EMERGING-LABS`):

```bash
docker-compose up -d --build
```

Open:

- App: `http://localhost:8000`

Login:

- `admin / admin123`

## Common Docker Commands

```bash
# start existing containers
docker-compose start

# stop containers
docker-compose stop

# stop + remove containers and compose network
docker-compose down --remove-orphans

# show container status
docker-compose ps

# follow logs
docker-compose logs -f app
docker-compose logs -f telemetry-publisher telemetry-db-consumer telemetry-app-consumer
```

## Local App Run (without running app container)

If Postgres is running from compose (`5433` on host):

```bash
DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5433/project" uvicorn app.main:app --reload
```

## Important Endpoints

Pages:

- `/` home
- `/login`, `/register`, `/logout`
- `/dashboard`
- `/equipments`, `/places`, `/roles`, `/users`
- `/di/...` and `/inspection/...`

Telemetry APIs:

- `GET /api/telemetry/components`
- `POST /api/telemetry/publish`
- `POST /api/telemetry/live`
- `GET /api/telemetry/dashboard`
- `GET /api/telemetry/alerts`

## Tech Stack

- Python 3.12
- FastAPI + Jinja2
- SQLAlchemy + psycopg2
- PostgreSQL
- Redpanda (Kafka API compatible)
- kafka-python
- Docker + docker-compose

## Known Operational Notes

- Postgres host port is intentionally `5433` to avoid common `5432` conflicts.
- If using legacy `docker-compose` v1, recreate can occasionally fail with `ContainerConfig`.
  - fix with full recycle:

```bash
docker-compose down --remove-orphans
docker-compose up -d --build
```

- Current startup uses `create_all` + bootstrap seeding; Alembic exists in repo for migration workflows.

## Suggested Next Improvements

- Move secrets (JWT secret, API keys, default credentials) to environment variables
- Add structured health checks for producer/consumers and topic lag
- Consolidate duplicate DI domains (`/di` and `/inspection`) into one canonical flow
- Run Alembic migrations automatically on startup/deploy in controlled environments
