"""
Schedule Models
Defines all data structures for events, schedules, and persistence.
"""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, time
from typing import Optional, Any
from enum import Enum


class EventType(str, Enum):
    VIDEO = "Video/Clip"
    TITLE = "Title/Lower Third"
    OVERLAY = "Overlay/Graphic"
    PLAYLIST = "Playlist"
    LIVE_INPUT = "Live Input"
    COMMAND = "vMix Command"


class TriggerType(str, Enum):
    TIME = "time"          # Fire at exact clock time
    CUE = "cue"            # Fire when previous event ends
    TIME_OR_CUE = "time_or_cue"  # Whichever comes first
    MANUAL = "manual"      # Only fire manually


class TransitionType(str, Enum):
    CUT = "Cut"
    FADE = "Fade"
    ZOOM = "Zoom"
    WIPE = "Wipe"
    SLIDE = "Slide"
    FLY = "Fly"
    CROSS_ZOOM = "CrossZoom"
    FLY_ROTATE = "FlyRotate"
    CUBE = "Cube"
    MERGE = "Merge"


class EventStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class TitleField:
    field_name: str
    value: str


@dataclass
class ScheduleEvent:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    event_type: EventType = EventType.VIDEO
    enabled: bool = True

    # Timing
    trigger_type: TriggerType = TriggerType.TIME
    scheduled_time: Optional[str] = None   # "HH:MM:SS"
    scheduled_date: Optional[str] = None   # "YYYY-MM-DD" or None for daily
    duration_seconds: Optional[int] = None # Expected duration, None = auto
    days_of_week: list = field(default_factory=lambda: [0,1,2,3,4,5,6])  # 0=Mon

    # vMix targeting
    input_number: Optional[int] = None
    input_name: str = ""
    overlay_channel: int = 1
    transition: TransitionType = TransitionType.CUT
    transition_duration_ms: int = 1000
    loop: bool = False
    volume: Optional[int] = None

    # Title-specific
    title_fields: list = field(default_factory=list)  # list of TitleField dicts

    # Overlay-specific
    overlay_action: str = "on"  # "on", "off", "toggle"

    # Playlist-specific
    playlist_action: str = "start"  # "start", "stop", "next", "previous"

    # Post-action
    post_action: str = "none"  # "none", "overlay_off", "next_event", "stop_all"
    post_action_delay_ms: int = 0

    # Notes
    notes: str = ""
    color: str = "#1565C0"  # display color in schedule grid

    # Runtime state (not persisted)
    status: EventStatus = EventStatus.PENDING
    actual_start_time: Optional[str] = None
    actual_end_time: Optional[str] = None
    error_message: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        d["trigger_type"] = self.trigger_type.value
        d["transition"] = self.transition.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ScheduleEvent":
        d = dict(d)
        d["event_type"] = EventType(d.get("event_type", EventType.VIDEO.value))
        d["trigger_type"] = TriggerType(d.get("trigger_type", TriggerType.TIME.value))
        d["transition"] = TransitionType(d.get("transition", TransitionType.CUT.value))
        d["status"] = EventStatus(d.get("status", EventStatus.PENDING.value))
        return cls(**d)

    def get_scheduled_datetime(self, date: datetime = None) -> Optional[datetime]:
        """Get the next scheduled datetime for this event."""
        if not self.scheduled_time:
            return None
        date = date or datetime.now()
        t = datetime.strptime(self.scheduled_time, "%H:%M:%S").time()
        if self.scheduled_date:
            d = datetime.strptime(self.scheduled_date, "%Y-%m-%d")
            return datetime.combine(d.date(), t)
        return datetime.combine(date.date(), t)

    def is_scheduled_today(self) -> bool:
        today = datetime.now().weekday()
        return today in (self.days_of_week or [0,1,2,3,4,5,6])

    def reset_status(self):
        self.status = EventStatus.PENDING
        self.actual_start_time = None
        self.actual_end_time = None
        self.error_message = ""


@dataclass
class Schedule:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "My Schedule"
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    modified_at: str = field(default_factory=lambda: datetime.now().isoformat())
    events: list = field(default_factory=list)  # list of ScheduleEvent

    # Settings
    auto_run: bool = False
    loop_schedule: bool = True
    vmix_host: str = "localhost"
    vmix_port: int = 8088

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "auto_run": self.auto_run,
            "loop_schedule": self.loop_schedule,
            "vmix_host": self.vmix_host,
            "vmix_port": self.vmix_port,
            "events": [e.to_dict() for e in self.events],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Schedule":
        events = [ScheduleEvent.from_dict(e) for e in d.get("events", [])]
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            name=d.get("name", "Schedule"),
            description=d.get("description", ""),
            created_at=d.get("created_at", ""),
            modified_at=d.get("modified_at", ""),
            auto_run=d.get("auto_run", False),
            loop_schedule=d.get("loop_schedule", True),
            vmix_host=d.get("vmix_host", "localhost"),
            vmix_port=d.get("vmix_port", 8088),
            events=events,
        )

    def save(self, filepath: str):
        self.modified_at = datetime.now().isoformat()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, filepath: str) -> "Schedule":
        with open(filepath, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def get_events_sorted(self) -> list:
        """Return events sorted by scheduled time."""
        def sort_key(e):
            if e.scheduled_time:
                return e.scheduled_time
            return "99:99:99"
        return sorted(self.events, key=sort_key)

    def add_event(self, event: ScheduleEvent):
        self.events.append(event)

    def remove_event(self, event_id: str):
        self.events = [e for e in self.events if e.id != event_id]

    def get_event(self, event_id: str) -> Optional[ScheduleEvent]:
        for e in self.events:
            if e.id == event_id:
                return e
        return None

    def reset_all_statuses(self):
        for e in self.events:
            e.reset_status()


# ── Event Log ──────────────────────────────────────────────────────────────

@dataclass
class LogEntry:
    timestamp: str
    level: str  # "info", "warning", "error", "success"
    message: str
    event_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class EventLog:
    def __init__(self, max_entries: int = 500):
        self.entries: list[LogEntry] = []
        self.max_entries = max_entries
        self._callbacks = []

    def add(self, level: str, message: str, event_id: str = None):
        entry = LogEntry(
            timestamp=datetime.now().strftime("%H:%M:%S"),
            level=level,
            message=message,
            event_id=event_id,
        )
        self.entries.append(entry)
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]
        for cb in list(self._callbacks):
            try:
                cb(entry)
            except Exception:
                pass

    def info(self, msg, event_id=None): self.add("info", msg, event_id)
    def warning(self, msg, event_id=None): self.add("warning", msg, event_id)
    def error(self, msg, event_id=None): self.add("error", msg, event_id)
    def success(self, msg, event_id=None): self.add("success", msg, event_id)

    def add_callback(self, cb): self._callbacks.append(cb)
    def remove_callback(self, cb): self._callbacks = [c for c in self._callbacks if c != cb]

    def get_recent(self, n: int = 50) -> list:
        return self.entries[-n:]

    def clear(self): self.entries.clear()
