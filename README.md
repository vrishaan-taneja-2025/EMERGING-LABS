# EMERGING-LABS

Datacenter inspection web app with live telemetry streaming.

## Stack

- FastAPI app (`app`) on port `8000`
- Postgres (`db`) on host port `5433`
- Kafka-compatible broker (`kafka` via Redpanda)
- Telemetry producer (`telemetry-publisher`)
- Telemetry DB consumer (`telemetry-db-consumer`)
- Telemetry app consumer (`telemetry-app-consumer`)

## Telemetry Architecture

One topic, two subscribers:

- Producer publishes random telemetry every **5 seconds** to topic `telemetry.raw`
- Consumer group `telemetry-db-writer` writes telemetry to Postgres
- Consumer group `telemetry-app-updater` forwards telemetry to app live endpoint for dashboard refresh

## Quick Start (Docker)

From project root:

```bash
docker-compose up -d --build
```

Open app:

- `http://localhost:8000`

Default login:

- Username: `admin`
- Password: `admin123`

## Common Commands

```bash
# Start existing containers
docker-compose start

# Stop containers
docker-compose stop

# See service status
docker-compose ps

# Tail logs
docker-compose logs -f app
docker-compose logs -f telemetry-publisher telemetry-db-consumer telemetry-app-consumer

# Full reset of this compose project
docker-compose down --remove-orphans
```

## Local Development (without Docker app)

If DB is running in Docker on host port `5433`, run:

```bash
DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5433/project" uvicorn app.main:app --reload
```

## Notes

- `db` is exposed as `5433:5432` to avoid host `5432` conflicts.
- Dashboard polling refresh is every 5 seconds.
- Startup bootstrap seeds required auth roles/user and demo telemetry entities if missing.

## Troubleshooting

### 1) `address already in use` for Postgres

You likely have something using host port `5432`. This project uses `5433` to avoid that.

### 2) `docker-compose` error: `'ContainerConfig'`

This is a known issue with older Compose v1 during recreate. Run:

```bash
docker-compose down --remove-orphans
docker-compose up -d --build
```

### 3) Login redirects back to login

Ensure services are fully up and app startup completed:

```bash
docker-compose logs -f app
```

Then log in with default credentials above.
