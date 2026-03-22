import json
import os
import random
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from kafka import KafkaProducer
from kafka.errors import KafkaError


BASE_URL = os.getenv("TELEMETRY_BASE_URL", "http://app:8000")
API_KEY = os.getenv("TELEMETRY_API_KEY", "local-telemetry-key")
POLL_INTERVAL_SECONDS = float(os.getenv("TELEMETRY_PUBLISH_INTERVAL", "5"))
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TELEMETRY_TOPIC = os.getenv("KAFKA_TELEMETRY_TOPIC", "telemetry.raw")


def request_json(url: str, method: str = "GET", payload: dict | None = None):
    data = None
    headers = {
        "Content-Type": "application/json",
        "x-telemetry-key": API_KEY,
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def maybe_anomalous(value: float, step: tuple[float, float], anomaly_delta: tuple[float, float], anomaly_rate: float = 0.15):
    if random.random() < anomaly_rate:
        direction = random.choice([-1, 1])
        delta = random.uniform(*anomaly_delta)
        return round(value + (direction * delta), 2)
    return round(value + random.uniform(*step), 2)


def build_payload(component: dict):
    component_type = component["component_type"]
    if component_type == "battery":
        payload = {
            "equipment_id": component["equipment_id"],
            "component_type": component_type,
            "status": component["status"],
            "voltage": maybe_anomalous(12.8, (-0.4, 0.4), (1.5, 3.0)),
            "temperature": maybe_anomalous(28.0, (-3.0, 3.0), (12.0, 20.0)),
        }
    else:
        payload = {
            "equipment_id": component["equipment_id"],
            "component_type": component_type,
            "status": component["status"],
            "temperature": maybe_anomalous(24.0, (-2.0, 2.0), (10.0, 16.0)),
            "voltage": maybe_anomalous(230.0, (-5.0, 5.0), (25.0, 40.0)),
            "frequency": maybe_anomalous(50.0, (-0.4, 0.4), (2.0, 4.5)),
            "pressure": maybe_anomalous(1.5, (-0.2, 0.2), (1.5, 2.5)),
        }

    payload["equipment_name"] = component.get("name")
    payload["topic"] = component.get("topic")
    payload["published_at"] = datetime.now(timezone.utc).isoformat()
    return payload


def create_producer() -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda value: json.dumps(value).encode("utf-8"),
        linger_ms=200,
    )


def main():
    print(f"Telemetry publisher targeting {BASE_URL}")
    print(f"Kafka producer bootstrap={KAFKA_BOOTSTRAP_SERVERS} topic={KAFKA_TELEMETRY_TOPIC}")

    producer = None
    while producer is None:
        try:
            producer = create_producer()
        except Exception as exc:
            print("producer init error", exc)
            time.sleep(2)

    while True:
        try:
            response = request_json(f"{BASE_URL}/api/telemetry/components")
            components = response.get("components", [])

            for component in components:
                if component.get("status", "").lower() != "on":
                    continue

                payload = build_payload(component)
                producer.send(KAFKA_TELEMETRY_TOPIC, payload)
                print("published", payload["equipment_id"], payload)

            producer.flush(timeout=10)

        except (urllib.error.URLError, KafkaError) as exc:
            print("publisher error", exc)
        except Exception as exc:
            print("publisher unexpected error", exc)

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
