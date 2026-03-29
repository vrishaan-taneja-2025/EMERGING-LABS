import argparse
import json

import app.models  # noqa: F401

from app.core.bootstrap import ensure_default_auth_data, ensure_default_telemetry_entities, ensure_demo_data
from app.core.bulk_demo_data import BulkDemoConfig, load_bulk_demo_config_from_env, seed_bulk_demo_data
from app.db.session import SessionLocal


def parse_args() -> argparse.Namespace:
    env_config = load_bulk_demo_config_from_env()
    parser = argparse.ArgumentParser(
        description="Seed base app data plus large historical demo data for analytics and Tableau."
    )
    parser.add_argument("--days", type=int, default=env_config.days)
    parser.add_argument("--samples-per-day", type=int, default=env_config.samples_per_day)
    parser.add_argument("--server-racks-per-hall", type=int, default=env_config.server_racks_per_hall)
    parser.add_argument("--battery-banks", type=int, default=env_config.battery_banks)
    parser.add_argument("--ups-units", type=int, default=env_config.ups_units)
    parser.add_argument("--cooling-units", type=int, default=env_config.cooling_units)
    parser.add_argument("--network-devices", type=int, default=env_config.network_devices)
    parser.add_argument("--inspections-per-day", type=int, default=env_config.inspections_per_day)
    parser.add_argument("--random-seed", type=int, default=env_config.random_seed)
    return parser.parse_args()


def main():
    args = parse_args()
    db = SessionLocal()
    try:
        ensure_default_auth_data(db)
        ensure_default_telemetry_entities(db)
        ensure_demo_data(db)
        summary = seed_bulk_demo_data(
            db,
            BulkDemoConfig(
                days=args.days,
                samples_per_day=args.samples_per_day,
                server_racks_per_hall=args.server_racks_per_hall,
                battery_banks=args.battery_banks,
                ups_units=args.ups_units,
                cooling_units=args.cooling_units,
                network_devices=args.network_devices,
                inspections_per_day=args.inspections_per_day,
                random_seed=args.random_seed,
            ),
        )
        print("Demo data seeded successfully")
        print(json.dumps(summary, indent=2, sort_keys=True))
    finally:
        db.close()


if __name__ == "__main__":
    main()
