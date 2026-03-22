import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from kafka import KafkaConsumer

import app.models  # noqa: F401
from app.core.telemetry import TelemetryEvent, build_topic, detect_anomaly, normalize_component_type
from app.db.session import SessionLocal
from app.models.equipment import Equipment
from app.models.telemetry_alert import TelemetryAlert
from app.models.telemetry_record import TelemetryRecord


KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TELEMETRY_TOPIC = os.getenv("KAFKA_TELEMETRY_TOPIC", "telemetry.raw")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "telemetry-consumer")
TELEMETRY_CONSUMER_MODE = os.getenv("TELEMETRY_CONSUMER_MODE", "db").strip().lower()
TELEMETRY_API_KEY = os.getenv("TELEMETRY_API_KEY", "local-telemetry-key")
TELEMETRY_APP_BASE_URL = os.getenv("TELEMETRY_APP_BASE_URL", "http://app:8000")


def parse_published_at(raw_value: str | None) -> datetime:
    if not raw_value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def post_json(url: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-telemetry-key": TELEMETRY_API_KEY,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10):
        return


def handle_db_message(payload: dict):
    equipment_id = payload.get("equipment_id")
    if not equipment_id:
        return

    db = SessionLocal()
    try:
        equipment = db.query(Equipment).filter(Equipment.id == int(equipment_id)).first()
        if not equipment:
            return

        component_type = normalize_component_type(payload.get("component_type"))
        event = TelemetryEvent(
            equipment_id=equipment.id,
            equipment_name=payload.get("equipment_name") or equipment.name,
            component_type=component_type,
            topic=payload.get("topic") or build_topic(component_type, equipment.id),
            status=payload.get("status") or "Off",
            temperature=payload.get("temperature"),
            voltage=payload.get("voltage"),
            pressure=payload.get("pressure"),
            frequency=payload.get("frequency"),
            published_at=parse_published_at(payload.get("published_at")),
        )

        anomaly_message = detect_anomaly(event)
        record = TelemetryRecord(
            equipment_id=event.equipment_id,
            topic=event.topic,
            component_type=event.component_type,
            status=event.status,
            temperature=event.temperature,
            voltage=event.voltage,
            pressure=event.pressure,
            frequency=event.frequency,
            is_anomaly=anomaly_message is not None,
            anomaly_message=anomaly_message,
        )
        db.add(record)

        existing_alert = (
            db.query(TelemetryAlert)
            .filter(
                TelemetryAlert.equipment_id == event.equipment_id,
                TelemetryAlert.is_active.is_(True),
            )
            .first()
        )

        if anomaly_message:
            if existing_alert:
                existing_alert.message = anomaly_message
                existing_alert.created_at = datetime.now(timezone.utc)
            else:
                db.add(TelemetryAlert(
                    equipment_id=event.equipment_id,
                    severity="critical",
                    title=f"Telemetry anomaly on {event.equipment_name}",
                    message=anomaly_message,
                    is_active=True,
                ))
        elif existing_alert:
            existing_alert.is_active = False

        db.commit()
    finally:
        db.close()


def handle_app_message(payload: dict):
    post_json(f"{TELEMETRY_APP_BASE_URL}/api/telemetry/live", payload)


def create_consumer() -> KafkaConsumer:
    return KafkaConsumer(
        KAFKA_TELEMETRY_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=KAFKA_GROUP_ID,
        auto_offset_reset="latest",
        enable_auto_commit=True,
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
    )


def main():
    print(
        "Starting consumer",
        f"mode={TELEMETRY_CONSUMER_MODE}",
        f"topic={KAFKA_TELEMETRY_TOPIC}",
        f"group={KAFKA_GROUP_ID}",
    )

    while True:
        try:
            consumer = create_consumer()
            break
        except Exception as exc:
            print("consumer init error", exc)
            time.sleep(2)

    for message in consumer:
        payload = message.value or {}
        try:
            if TELEMETRY_CONSUMER_MODE == "app":
                handle_app_message(payload)
            else:
                handle_db_message(payload)
        except urllib.error.URLError as exc:
            print("consumer app-forward error", exc)
        except Exception as exc:
            print("consumer processing error", exc)


if __name__ == "__main__":
    main()
