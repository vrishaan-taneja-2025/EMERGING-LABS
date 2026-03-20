import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock

from sqlalchemy.orm import joinedload

from app.db.session import SessionLocal
from app.models.equipment import Equipment
from app.models.telemetry_alert import TelemetryAlert
from app.models.telemetry_record import TelemetryRecord


TELEMETRY_API_KEY = os.getenv("TELEMETRY_API_KEY", "local-telemetry-key")


@dataclass
class TelemetryEvent:
    equipment_id: int
    equipment_name: str
    component_type: str
    topic: str
    status: str
    temperature: float | None = None
    voltage: float | None = None
    pressure: float | None = None
    frequency: float | None = None
    published_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def normalize_component_type(type_name: str | None) -> str:
    name = (type_name or "").strip().lower()
    if "battery" in name:
        return "battery"
    if "server" in name:
        return "server"
    return "server"


def build_topic(component_type: str, equipment_id: int) -> str:
    return f"telemetry/{component_type}/{equipment_id}"


def detect_anomaly(event: TelemetryEvent) -> str | None:
    if event.component_type == "battery":
        messages = []
        if event.voltage is not None and not 11.8 <= event.voltage <= 14.8:
            messages.append(f"voltage={event.voltage:.2f}V")
        if event.temperature is not None and not 18 <= event.temperature <= 42:
            messages.append(f"temperature={event.temperature:.2f}C")
        if messages:
            return "Battery anomaly: " + ", ".join(messages)
        return None

    messages = []
    if event.temperature is not None and not 18 <= event.temperature <= 32:
        messages.append(f"temperature={event.temperature:.2f}C")
    if event.voltage is not None and not 210 <= event.voltage <= 240:
        messages.append(f"voltage={event.voltage:.2f}V")
    if event.frequency is not None and not 49 <= event.frequency <= 51:
        messages.append(f"frequency={event.frequency:.2f}Hz")
    if event.pressure is not None and not 0.8 <= event.pressure <= 2.5:
        messages.append(f"pressure={event.pressure:.2f}")
    if messages:
        return "Server anomaly: " + ", ".join(messages)
    return None


class TelemetryHub:
    def __init__(self):
        self._recorder_queue: asyncio.Queue[TelemetryEvent] = asyncio.Queue()
        self._dashboard_queue: asyncio.Queue[TelemetryEvent] = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []
        self._latest_events: dict[int, TelemetryEvent] = {}
        self._dashboard_cache: dict[int, dict] = {}
        self._lock = Lock()

    async def start(self):
        if self._tasks:
            return
        self._tasks = [
            asyncio.create_task(self._recorder_loop(), name="telemetry-recorder"),
            asyncio.create_task(self._dashboard_loop(), name="telemetry-dashboard"),
        ]

    async def stop(self):
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def publish(self, event: TelemetryEvent):
        await self._recorder_queue.put(event)
        await self._dashboard_queue.put(event)

    def snapshot(self):
        with self._lock:
            return list(self._dashboard_cache.values())

    async def _recorder_loop(self):
        while True:
            event = await self._recorder_queue.get()
            anomaly_message = detect_anomaly(event)
            db = SessionLocal()
            try:
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
                self._recorder_queue.task_done()

    async def _dashboard_loop(self):
        last_flush = datetime.now(timezone.utc)

        while True:
            timeout = max(0.1, 5 - (datetime.now(timezone.utc) - last_flush).total_seconds())
            try:
                event = await asyncio.wait_for(self._dashboard_queue.get(), timeout=timeout)
                self._latest_events[event.equipment_id] = event
                self._dashboard_queue.task_done()
            except asyncio.TimeoutError:
                pass

            now = datetime.now(timezone.utc)
            if (now - last_flush).total_seconds() < 5:
                continue

            db = SessionLocal()
            try:
                equipment_ids = list(self._latest_events.keys())
                equipments = (
                    db.query(Equipment)
                    .options(joinedload(Equipment.place), joinedload(Equipment.equipment_type))
                    .filter(Equipment.id.in_(equipment_ids))
                    .all()
                ) if equipment_ids else []

                equipment_map = {eq.id: eq for eq in equipments}
                cache: dict[int, dict] = {}
                for equipment_id, event in self._latest_events.items():
                    eq = equipment_map.get(equipment_id)
                    cache[equipment_id] = {
                        "id": equipment_id,
                        "name": event.equipment_name,
                        "topic": event.topic,
                        "component_type": event.component_type,
                        "status": event.status,
                        "temperature": event.temperature,
                        "voltage": event.voltage,
                        "pressure": event.pressure,
                        "frequency": event.frequency,
                        "place": eq.place.name if eq and eq.place else "-",
                        "type": eq.equipment_type.name if eq and eq.equipment_type else event.component_type,
                        "updated_at": event.published_at.isoformat(),
                        "is_anomaly": detect_anomaly(event) is not None,
                    }

                with self._lock:
                    self._dashboard_cache = cache
            finally:
                db.close()

            last_flush = now


telemetry_hub = TelemetryHub()
