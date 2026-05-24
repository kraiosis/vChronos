"""
Scheduler Engine
Manages the run loop, time-based and cue-based triggering,
and dispatches events to the vMix API.
"""

import threading
import time
from datetime import datetime, timedelta
from typing import Optional, Callable
from core.models import (
    Schedule, ScheduleEvent, EventType, TriggerType,
    EventStatus, TransitionType, EventLog
)
from core.vmix_api import VMixAPI, VMixState


class SchedulerEngine:
    """
    Core scheduling engine. Runs a tight loop checking:
      - Time-based triggers (fires at wall clock time)
      - Cue-based triggers (fires when previous event completes)
    """

    def __init__(self, api: VMixAPI, log: EventLog):
        self.api = api
        self.log = log
        self.schedule: Optional[Schedule] = None

        self._running = False
        self._paused = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Current state
        self._current_event_idx: int = -1
        self._current_event_start: Optional[datetime] = None
        self._cue_ready: bool = False       # True when previous event finished

        # Callbacks for UI updates
        self.on_event_started: Optional[Callable] = None
        self.on_event_completed: Optional[Callable] = None
        self.on_event_error: Optional[Callable] = None
        self.on_status_changed: Optional[Callable] = None
        self.on_tick: Optional[Callable] = None  # called every second

        # VMix state tracking
        self._last_vmix_state: Optional[VMixState] = None
        self.api.add_poll_callback(self._on_vmix_state)

    @property
    def is_running(self) -> bool:
        return self._running and not self._paused

    @property
    def is_paused(self) -> bool:
        return self._paused

    def load_schedule(self, schedule: Schedule):
        with self._lock:
            self.schedule = schedule
            self._current_event_idx = -1
            self._current_event_start = None
            self._cue_ready = False
            if schedule:
                schedule.reset_all_statuses()
        self.log.info(f"Schedule loaded: {schedule.name} ({len(schedule.events)} events)")

    def start(self):
        if self._running:
            return
        if not self.schedule:
            self.log.error("No schedule loaded")
            return
        self._running = True
        self._paused = False
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self.log.success("Scheduler started")
        self._notify_status()

    def stop(self):
        self._running = False
        self._paused = False
        self._current_event_idx = -1
        self._cue_ready = False
        if self.schedule:
            self.schedule.reset_all_statuses()
        self.log.warning("Scheduler stopped")
        self._notify_status()

    def pause(self):
        if self._running and not self._paused:
            self._paused = True
            self.log.info("Scheduler paused")
            self._notify_status()

    def resume(self):
        if self._running and self._paused:
            self._paused = False
            self.log.info("Scheduler resumed")
            self._notify_status()

    def skip_current(self):
        """Skip the currently running or next pending event."""
        with self._lock:
            if self.schedule and 0 <= self._current_event_idx < len(self.schedule.events):
                events = self.schedule.get_events_sorted()
                if self._current_event_idx < len(events):
                    ev = events[self._current_event_idx]
                    ev.status = EventStatus.SKIPPED
                    self.log.warning(f"Skipped: {ev.name}", ev.id)
                    self._cue_ready = True  # advance to next

    def fire_event_now(self, event_id: str):
        """Manually fire a specific event immediately."""
        if not self.schedule:
            return
        ev = self.schedule.get_event(event_id)
        if ev:
            threading.Thread(
                target=self._execute_event, args=(ev,), daemon=True
            ).start()

    def _run_loop(self):
        """Main scheduler loop - runs every 0.25 seconds."""
        while self._running:
            if not self._paused and self.schedule:
                try:
                    self._check_and_fire()
                except Exception as e:
                    self.log.error(f"Scheduler loop error: {e}")
            if self.on_tick:
                try:
                    self.on_tick()
                except Exception:
                    pass
            time.sleep(0.25)

    def _check_and_fire(self):
        """Check if any events need to be fired."""
        now = datetime.now()
        events = self.schedule.get_events_sorted()
        if not events:
            return

        for idx, ev in enumerate(events):
            if not ev.enabled:
                continue
            if ev.status in (EventStatus.RUNNING, EventStatus.COMPLETED,
                             EventStatus.SKIPPED):
                continue
            if not ev.is_scheduled_today():
                continue

            should_fire = False

            # Time-based check
            if ev.trigger_type in (TriggerType.TIME, TriggerType.TIME_OR_CUE):
                if ev.scheduled_time:
                    sched_dt = ev.get_scheduled_datetime(now)
                    if sched_dt and now >= sched_dt:
                        # Within 5 second window (prevents re-firing on restart)
                        diff = (now - sched_dt).total_seconds()
                        if 0 <= diff <= 5:
                            should_fire = True

            # Cue-based check
            if ev.trigger_type in (TriggerType.CUE, TriggerType.TIME_OR_CUE):
                if self._cue_ready and idx == self._current_event_idx + 1:
                    should_fire = True

            if should_fire:
                with self._lock:
                    self._current_event_idx = idx
                    self._cue_ready = False
                    ev.status = EventStatus.RUNNING
                    ev.actual_start_time = now.strftime("%H:%M:%S")
                    self._current_event_start = now

                threading.Thread(
                    target=self._execute_event, args=(ev,), daemon=True
                ).start()
                break  # only fire one event at a time

    def _execute_event(self, ev: ScheduleEvent):
        """Execute a single scheduled event against the vMix API."""
        self.log.info(f"▶ Firing: {ev.name} ({ev.event_type.value})", ev.id)
        if self.on_event_started:
            try:
                self.on_event_started(ev)
            except Exception:
                pass

        success = False
        try:
            success = self._dispatch(ev)
        except Exception as e:
            ev.error_message = str(e)
            self.log.error(f"Error executing {ev.name}: {e}", ev.id)

        ev.actual_end_time = datetime.now().strftime("%H:%M:%S")

        if success:
            ev.status = EventStatus.COMPLETED
            self.log.success(f"✓ Completed: {ev.name}", ev.id)
            # Handle duration-based cue
            if ev.duration_seconds and ev.duration_seconds > 0:
                threading.Thread(
                    target=self._wait_and_cue,
                    args=(ev.duration_seconds,),
                    daemon=True
                ).start()
            else:
                self._cue_ready = True
        else:
            ev.status = EventStatus.ERROR
            self._cue_ready = True  # advance even on error

        if self.on_event_completed:
            try:
                self.on_event_completed(ev)
            except Exception:
                pass

        self._execute_post_action(ev)

    def _dispatch(self, ev: ScheduleEvent) -> bool:
        """Dispatch the event to the appropriate vMix API calls."""
        inp = ev.input_number
        t = ev.transition.value
        dur = ev.transition_duration_ms

        if ev.event_type == EventType.VIDEO:
            if inp:
                self.api.set_preview(inp)
                time.sleep(0.05)
            ok = self.api.transition(t, inp, dur)
            if ok and inp:
                if ev.loop:
                    self.api.set_loop(inp, True)
                if ev.volume is not None:
                    self.api.set_volume(inp, ev.volume)
            return ok

        elif ev.event_type == EventType.LIVE_INPUT:
            if inp:
                self.api.set_preview(inp)
                time.sleep(0.05)
            return self.api.transition(t, inp, dur)

        elif ev.event_type == EventType.TITLE:
            # First set title fields, then transition
            if inp and ev.title_fields:
                for tf in ev.title_fields:
                    if isinstance(tf, dict):
                        fname = tf.get("field_name", "")
                        fval = tf.get("value", "")
                    else:
                        fname, fval = tf.field_name, tf.value
                    if fname:
                        self.api.set_title_text(inp, fname, fval)
                        time.sleep(0.03)
            if inp:
                self.api.set_preview(inp)
                time.sleep(0.05)
            return self.api.transition(t, inp, dur)

        elif ev.event_type == EventType.OVERLAY:
            ch = ev.overlay_channel or 1
            if ev.overlay_action == "on":
                return self.api.overlay_input_on(ch, inp) if inp else False
            elif ev.overlay_action == "off":
                return self.api.overlay_input_off(ch)
            elif ev.overlay_action == "toggle":
                return self.api.overlay_input_toggle(ch, inp) if inp else False

        elif ev.event_type == EventType.PLAYLIST:
            action = ev.playlist_action
            if action == "start":
                return self.api.start_playlist()
            elif action == "stop":
                return self.api.stop_playlist()
            elif action == "next":
                return self.api.next_playlist_item()
            elif action == "previous":
                return self.api.previous_playlist_item()

        elif ev.event_type == EventType.COMMAND:
            # Raw vMix function call via notes field
            # Format: FUNCTION_NAME param1=val1 param2=val2
            return self._execute_raw_command(ev.notes)

        return False

    def _execute_raw_command(self, cmd_str: str) -> bool:
        parts = cmd_str.strip().split()
        if not parts:
            return False
        fn = parts[0]
        kwargs = {}
        for part in parts[1:]:
            if "=" in part:
                k, v = part.split("=", 1)
                kwargs[k] = v
        return self.api.send_function(fn, **kwargs)

    def _execute_post_action(self, ev: ScheduleEvent):
        if not ev.post_action or ev.post_action == "none":
            return
        delay = ev.post_action_delay_ms / 1000.0
        if delay > 0:
            time.sleep(delay)
        if ev.post_action == "overlay_off":
            self.api.overlay_input_off(ev.overlay_channel or 1)
        elif ev.post_action == "stop_all":
            self.stop()

    def _wait_and_cue(self, seconds: float):
        """Wait for the event duration then signal cue ready."""
        time.sleep(seconds)
        self._cue_ready = True

    def _on_vmix_state(self, state: VMixState):
        self._last_vmix_state = state

    def _notify_status(self):
        if self.on_status_changed:
            try:
                self.on_status_changed()
            except Exception:
                pass

    def get_next_event(self) -> Optional[ScheduleEvent]:
        if not self.schedule:
            return None
        events = self.schedule.get_events_sorted()
        for ev in events:
            if ev.enabled and ev.status == EventStatus.PENDING:
                return ev
        return None

    def get_current_event(self) -> Optional[ScheduleEvent]:
        if not self.schedule:
            return None
        events = self.schedule.get_events_sorted()
        if 0 <= self._current_event_idx < len(events):
            return events[self._current_event_idx]
        return None

    def get_time_until_next(self) -> Optional[timedelta]:
        ev = self.get_next_event()
        if not ev or not ev.scheduled_time:
            return None
        now = datetime.now()
        sched = ev.get_scheduled_datetime(now)
        if sched and sched > now:
            return sched - now
        return None
