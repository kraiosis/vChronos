"""
vChronos v1.0 - vMix Automation Scheduler
Main Flet UI Application
Author: Federico Guzman (github.com/kraiosis)
"""

import flet as ft
import threading
import os
import json
from datetime import datetime
from typing import Optional

from core.vmix_api import VMixAPI
from core.models import (
    Schedule, ScheduleEvent, EventType, TriggerType,
    TransitionType, EventStatus, EventLog, TitleField
)
from core.scheduler import SchedulerEngine


# ── Color Palette ──────────────────────────────────────────────────────────

BG_DARK     = "#0A0E1A"
BG_CARD     = "#111827"
BG_SURFACE  = "#1A2235"
BG_ELEVATED = "#1F2D42"
ACCENT_BLUE = "#2563EB"
ACCENT_CYAN = "#06B6D4"
ACCENT_GREEN= "#10B981"
ACCENT_RED  = "#EF4444"
ACCENT_AMBER= "#F59E0B"
ACCENT_PURPLE="#8B5CF6"
TEXT_PRIMARY= "#F1F5F9"
TEXT_SECONDARY="#94A3B8"
TEXT_DIM    = "#475569"
BORDER      = "#1E3A5F"

EVENT_COLORS = {
    EventType.VIDEO:       "#1D4ED8",
    EventType.TITLE:       "#7C3AED",
    EventType.OVERLAY:     "#0F766E",
    EventType.PLAYLIST:    "#B45309",
    EventType.LIVE_INPUT:  "#B91C1C",
    EventType.COMMAND:     "#374151",
}

STATUS_COLORS = {
    EventStatus.PENDING:   TEXT_DIM,
    EventStatus.RUNNING:   ACCENT_CYAN,
    EventStatus.COMPLETED: ACCENT_GREEN,
    EventStatus.SKIPPED:   ACCENT_AMBER,
    EventStatus.ERROR:     ACCENT_RED,
}

STATUS_ICONS = {
    EventStatus.PENDING:   ft.Icons.SCHEDULE,
    EventStatus.RUNNING:   ft.Icons.PLAY_CIRCLE,
    EventStatus.COMPLETED: ft.Icons.CHECK_CIRCLE,
    EventStatus.SKIPPED:   ft.Icons.SKIP_NEXT,
    EventStatus.ERROR:     ft.Icons.ERROR,
}

LOG_COLORS = {
    "info":    TEXT_SECONDARY,
    "warning": ACCENT_AMBER,
    "error":   ACCENT_RED,
    "success": ACCENT_GREEN,
}


def main(page: ft.Page):
    page.title = "vChronos v1.0.0 - vMix Automation Scheduler"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BG_DARK
    page.padding = 0
    page.fonts = {
        "mono": "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&display=swap"
    }
    page.window.min_width = 1100
    page.window.min_height = 700

    # ── Application State ──────────────────────────────────────────────────

    api = VMixAPI()
    log = EventLog()
    engine = SchedulerEngine(api, log)
    schedule = Schedule(name="New Schedule")
    engine.load_schedule(schedule)
    current_file_path: list = [None]  # mutable ref

    selected_event_id: list = [None]
    edit_dialog_open: list = [False]

    # ── Header ─────────────────────────────────────────────────────────────

    vmix_status_dot = ft.Container(
        width=10, height=10, border_radius=5,
        bgcolor=ACCENT_RED,
        tooltip="vMix disconnected"
    )
    vmix_status_text = ft.Text("Disconnected", size=12, color=ACCENT_RED)
    schedule_name_text = ft.Text("New Schedule", size=14,
                                  weight=ft.FontWeight.W_600, color=TEXT_PRIMARY)
    clock_text = ft.Text("00:00:00", size=18, weight=ft.FontWeight.W_700,
                          color=ACCENT_CYAN,
                          font_family="mono")
    run_btn = ft.Button(
        "▶  START", bgcolor=ACCENT_GREEN, color="white",
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6)),
        height=36
    )
    pause_btn = ft.Button(
        "⏸  PAUSE", bgcolor=ACCENT_AMBER, color="white",
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6)),
        height=36, disabled=True
    )
    stop_btn = ft.Button(
        "⏹  STOP", bgcolor=ACCENT_RED, color="white",
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6)),
        height=36, disabled=True
    )

    # ── Schedule Event List ─────────────────────────────────────────────────

    event_list_col = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        spacing=4,
        expand=True,
    )

    # ── Status Panel ───────────────────────────────────────────────────────

    now_playing_text = ft.Text("—", size=13, color=ACCENT_CYAN, weight=ft.FontWeight.W_600)
    now_status_text  = ft.Text("Idle", size=12, color=TEXT_SECONDARY)
    next_event_text  = ft.Text("—", size=12, color=TEXT_SECONDARY)
    countdown_text   = ft.Text("—", size=22, color=ACCENT_CYAN,
                                weight=ft.FontWeight.W_700, font_family="mono")

    vmix_active_text   = ft.Text("—", size=12, color=TEXT_SECONDARY)
    vmix_preview_text  = ft.Text("—", size=12, color=TEXT_SECONDARY)
    vmix_rec_icon      = ft.Icon(ft.Icons.CIRCLE, size=12, color=TEXT_DIM)
    vmix_stream_icon   = ft.Icon(ft.Icons.CIRCLE, size=12, color=TEXT_DIM)

    # ── Log Panel ──────────────────────────────────────────────────────────

    log_col = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        spacing=2,
        expand=True,
    )

    # ── Connection Dialog ──────────────────────────────────────────────────

    conn_host_field = ft.TextField(
        value="localhost", label="vMix Host / IP",
        border_color=BORDER, bgcolor=BG_ELEVATED,
        color=TEXT_PRIMARY, label_style=ft.TextStyle(color=TEXT_SECONDARY),
        height=46, text_size=13,
    )
    conn_port_field = ft.TextField(
        value="8088", label="Port",
        border_color=BORDER, bgcolor=BG_ELEVATED,
        color=TEXT_PRIMARY, label_style=ft.TextStyle(color=TEXT_SECONDARY),
        height=46, text_size=13, width=100,
    )
    conn_status_text = ft.Text("", size=12)

    def do_connect(e):
        host = conn_host_field.value.strip() or "localhost"
        try:
            port = int(conn_port_field.value.strip())
        except Exception:
            port = 8088
        api.stop_polling()
        api.host = host
        api.port = port
        ok, msg = api.test_connection()
        conn_status_text.value = msg
        conn_status_text.color = ACCENT_GREEN if ok else ACCENT_RED
        if ok:
            api.start_polling(interval=1.5)
        page.update()

    conn_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Connect to vMix", color=TEXT_PRIMARY,
                       weight=ft.FontWeight.W_700),
        bgcolor=BG_CARD,
        content=ft.Column([
            ft.Row([conn_host_field, conn_port_field], spacing=8),
            ft.Button("Test & Connect", bgcolor=ACCENT_BLUE,
                              color="white", on_click=do_connect),
            conn_status_text,
        ], spacing=12, tight=True),
        actions=[
            ft.TextButton("Close", on_click=lambda e: close_dialog(conn_dialog)),
        ],
    )

    # ── Event Edit Dialog ──────────────────────────────────────────────────

    ev_name_field    = ft.TextField(label="Event Name", border_color=BORDER,
                                     bgcolor=BG_ELEVATED, color=TEXT_PRIMARY,
                                     label_style=ft.TextStyle(color=TEXT_SECONDARY))
    ev_type_dd       = ft.Dropdown(label="Event Type",
                                    border_color=BORDER, bgcolor=BG_ELEVATED,
                                    color=TEXT_PRIMARY,
                                    label_style=ft.TextStyle(color=TEXT_SECONDARY),
                                    options=[ft.dropdown.Option(t.value) for t in EventType])
    ev_input_field   = ft.TextField(label="Input Number", border_color=BORDER,
                                     bgcolor=BG_ELEVATED, color=TEXT_PRIMARY,
                                     label_style=ft.TextStyle(color=TEXT_SECONDARY),
                                     keyboard_type=ft.KeyboardType.NUMBER)
    ev_input_name_field = ft.TextField(label="Input Name (optional)", border_color=BORDER,
                                        bgcolor=BG_ELEVATED, color=TEXT_PRIMARY,
                                        label_style=ft.TextStyle(color=TEXT_SECONDARY))
    ev_time_field    = ft.TextField(label="Scheduled Time (HH:MM:SS)", border_color=BORDER,
                                     bgcolor=BG_ELEVATED, color=TEXT_PRIMARY,
                                     label_style=ft.TextStyle(color=TEXT_SECONDARY))
    ev_trigger_dd    = ft.Dropdown(label="Trigger",
                                    border_color=BORDER, bgcolor=BG_ELEVATED,
                                    color=TEXT_PRIMARY,
                                    label_style=ft.TextStyle(color=TEXT_SECONDARY),
                                    options=[ft.dropdown.Option(t.value) for t in TriggerType])
    ev_transition_dd = ft.Dropdown(label="Transition",
                                    border_color=BORDER, bgcolor=BG_ELEVATED,
                                    color=TEXT_PRIMARY,
                                    label_style=ft.TextStyle(color=TEXT_SECONDARY),
                                    options=[ft.dropdown.Option(t.value) for t in TransitionType])
    ev_trans_dur     = ft.TextField(label="Transition Duration (ms)", border_color=BORDER,
                                     bgcolor=BG_ELEVATED, color=TEXT_PRIMARY,
                                     label_style=ft.TextStyle(color=TEXT_SECONDARY),
                                     keyboard_type=ft.KeyboardType.NUMBER)
    ev_duration_field= ft.TextField(label="Event Duration (seconds, for cue)", border_color=BORDER,
                                     bgcolor=BG_ELEVATED, color=TEXT_PRIMARY,
                                     label_style=ft.TextStyle(color=TEXT_SECONDARY),
                                     keyboard_type=ft.KeyboardType.NUMBER)
    ev_overlay_ch    = ft.Dropdown(label="Overlay Channel",
                                    border_color=BORDER, bgcolor=BG_ELEVATED,
                                    color=TEXT_PRIMARY,
                                    label_style=ft.TextStyle(color=TEXT_SECONDARY),
                                    options=[ft.dropdown.Option(str(i)) for i in [1,2,3,4]])
    ev_overlay_action= ft.Dropdown(label="Overlay Action",
                                    border_color=BORDER, bgcolor=BG_ELEVATED,
                                    color=TEXT_PRIMARY,
                                    label_style=ft.TextStyle(color=TEXT_SECONDARY),
                                    options=[ft.dropdown.Option(a) for a in ["on","off","toggle"]])
    ev_playlist_action=ft.Dropdown(label="Playlist Action",
                                    border_color=BORDER, bgcolor=BG_ELEVATED,
                                    color=TEXT_PRIMARY,
                                    label_style=ft.TextStyle(color=TEXT_SECONDARY),
                                    options=[ft.dropdown.Option(a) for a in ["start","stop","next","previous"]])
    ev_title_fields_col = ft.Column(spacing=6)
    ev_notes_field   = ft.TextField(label="Notes / Raw Command", border_color=BORDER,
                                     bgcolor=BG_ELEVATED, color=TEXT_PRIMARY,
                                     label_style=ft.TextStyle(color=TEXT_SECONDARY),
                                     multiline=True, min_lines=2)
    ev_color_field   = ft.TextField(label="Color (hex)", border_color=BORDER,
                                     bgcolor=BG_ELEVATED, color=TEXT_PRIMARY,
                                     label_style=ft.TextStyle(color=TEXT_SECONDARY))
    ev_enabled_switch= ft.Switch(label="Enabled", value=True,
                                  active_color=ACCENT_CYAN)
    ev_loop_switch   = ft.Switch(label="Loop", value=False, active_color=ACCENT_CYAN)

    def add_title_field_row(fname="", fval=""):
        fn_tf = ft.TextField(
            value=fname, hint_text="Field name", expand=True,
            border_color=BORDER, bgcolor=BG_ELEVATED, color=TEXT_PRIMARY,
            hint_style=ft.TextStyle(color=TEXT_DIM), height=40, text_size=12,
        )
        fv_tf = ft.TextField(
            value=fval, hint_text="Value", expand=2,
            border_color=BORDER, bgcolor=BG_ELEVATED, color=TEXT_PRIMARY,
            hint_style=ft.TextStyle(color=TEXT_DIM), height=40, text_size=12,
        )
        row = ft.Row(
            [fn_tf, fv_tf,
             ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=ACCENT_RED,
                           icon_size=16,
                           on_click=lambda e, r=None: remove_title_row(e))
             ],
            spacing=6
        )
        # Tag for removal
        row.data = (fn_tf, fv_tf)
        ev_title_fields_col.controls.append(row)
        if page.overlay:
            page.update()

    def remove_title_row(e):
        btn = e.control
        for ctrl in ev_title_fields_col.controls[:]:
            if isinstance(ctrl, ft.Row) and btn in ctrl.controls:
                ev_title_fields_col.controls.remove(ctrl)
                break
        page.update()

    def populate_edit_dialog(ev: ScheduleEvent):
        ev_name_field.value = ev.name
        ev_type_dd.value = ev.event_type.value
        ev_input_field.value = str(ev.input_number) if ev.input_number else ""
        ev_input_name_field.value = ev.input_name
        ev_time_field.value = ev.scheduled_time or ""
        ev_trigger_dd.value = ev.trigger_type.value
        ev_transition_dd.value = ev.transition.value
        ev_trans_dur.value = str(ev.transition_duration_ms)
        ev_duration_field.value = str(ev.duration_seconds) if ev.duration_seconds else ""
        ev_overlay_ch.value = str(ev.overlay_channel)
        ev_overlay_action.value = ev.overlay_action
        ev_playlist_action.value = ev.playlist_action
        ev_notes_field.value = ev.notes
        ev_color_field.value = ev.color
        ev_enabled_switch.value = ev.enabled
        ev_loop_switch.value = ev.loop
        ev_title_fields_col.controls.clear()
        for tf in ev.title_fields:
            if isinstance(tf, dict):
                add_title_field_row(tf.get("field_name",""), tf.get("value",""))
            else:
                add_title_field_row(tf.field_name, tf.value)

    def save_edit_dialog():
        ev_id = selected_event_id[0]
        if not ev_id:
            ev = ScheduleEvent()
            schedule.add_event(ev)
            selected_event_id[0] = ev.id
        else:
            ev = schedule.get_event(ev_id)
            if not ev:
                return

        ev.name = ev_name_field.value.strip() or "Unnamed Event"
        try:
            ev.event_type = EventType(ev_type_dd.value)
        except Exception:
            pass
        ev.input_number = int(ev_input_field.value) if ev_input_field.value.strip().isdigit() else None
        ev.input_name = ev_input_name_field.value.strip()
        ev.scheduled_time = ev_time_field.value.strip() or None
        try:
            ev.trigger_type = TriggerType(ev_trigger_dd.value)
        except Exception:
            pass
        try:
            ev.transition = TransitionType(ev_transition_dd.value)
        except Exception:
            pass
        ev.transition_duration_ms = int(ev_trans_dur.value) if ev_trans_dur.value.strip().isdigit() else 1000
        ev.duration_seconds = int(ev_duration_field.value) if ev_duration_field.value.strip().isdigit() else None
        ev.overlay_channel = int(ev_overlay_ch.value) if ev_overlay_ch.value else 1
        ev.overlay_action = ev_overlay_action.value or "on"
        ev.playlist_action = ev_playlist_action.value or "start"
        ev.notes = ev_notes_field.value.strip()
        ev.color = ev_color_field.value.strip() or EVENT_COLORS.get(ev.event_type, ACCENT_BLUE)
        ev.enabled = ev_enabled_switch.value
        ev.loop = ev_loop_switch.value

        # Title fields
        ev.title_fields = []
        for row in ev_title_fields_col.controls:
            if isinstance(row, ft.Row) and row.data:
                fn_tf, fv_tf = row.data
                if fn_tf.value.strip():
                    ev.title_fields.append({
                        "field_name": fn_tf.value.strip(),
                        "value": fv_tf.value
                    })

        rebuild_event_list()
        log.info(f"Event saved: {ev.name}", ev.id)

    edit_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Edit Event", color=TEXT_PRIMARY, weight=ft.FontWeight.W_700),
        bgcolor=BG_CARD,
        content=ft.Container(
            width=640,
            content=ft.Column([
                ft.Row([ev_name_field, ev_type_dd], spacing=8),
                ft.Row([ev_input_field, ev_input_name_field], spacing=8),
                ft.Row([ev_time_field, ev_trigger_dd], spacing=8),
                ft.Row([ev_transition_dd, ev_trans_dur, ev_duration_field], spacing=8),
                ft.Row([ev_overlay_ch, ev_overlay_action, ev_playlist_action], spacing=8),
                ft.Text("Title Fields", size=12, color=TEXT_SECONDARY),
                ev_title_fields_col,
                ft.TextButton(
                    "+ Add Title Field",
                    on_click=lambda e: (add_title_field_row(), page.update()),
                    style=ft.ButtonStyle(color=ACCENT_CYAN)
                ),
                ev_notes_field,
                ft.Row([ev_color_field, ev_enabled_switch, ev_loop_switch], spacing=16),
            ], scroll=ft.ScrollMode.AUTO, spacing=10),
            height=480,
        ),
        actions=[
            ft.TextButton("Cancel",
                          on_click=lambda e: close_dialog(edit_dialog),
                          style=ft.ButtonStyle(color=TEXT_SECONDARY)),
            ft.Button(
                "Save", bgcolor=ACCENT_BLUE, color="white",
                on_click=lambda e: (save_edit_dialog(), close_dialog(edit_dialog))
            ),
        ],
    )

    # ── Schedule Settings Dialog ───────────────────────────────────────────

    sched_name_field = ft.TextField(
        label="Schedule Name", border_color=BORDER,
        bgcolor=BG_ELEVATED, color=TEXT_PRIMARY,
        label_style=ft.TextStyle(color=TEXT_SECONDARY)
    )
    sched_desc_field = ft.TextField(
        label="Description", border_color=BORDER,
        bgcolor=BG_ELEVATED, color=TEXT_PRIMARY,
        label_style=ft.TextStyle(color=TEXT_SECONDARY),
        multiline=True, min_lines=2
    )
    sched_loop_switch = ft.Switch(label="Loop Schedule", value=True, active_color=ACCENT_CYAN)
    sched_autorun_switch = ft.Switch(label="Auto-Run on Open", value=False, active_color=ACCENT_CYAN)

    def save_schedule_settings():
        schedule.name = sched_name_field.value.strip() or "Schedule"
        schedule.description = sched_desc_field.value.strip()
        schedule.loop_schedule = sched_loop_switch.value
        schedule.auto_run = sched_autorun_switch.value
        schedule_name_text.value = schedule.name
        page.update()

    settings_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Schedule Settings", color=TEXT_PRIMARY, weight=ft.FontWeight.W_700),
        bgcolor=BG_CARD,
        content=ft.Column([
            sched_name_field, sched_desc_field,
            ft.Row([sched_loop_switch, sched_autorun_switch], spacing=24),
        ], spacing=12, tight=True),
        actions=[
            ft.TextButton("Cancel", on_click=lambda e: close_dialog(settings_dialog),
                          style=ft.ButtonStyle(color=TEXT_SECONDARY)),
            ft.Button("Save", bgcolor=ACCENT_BLUE, color="white",
                              on_click=lambda e: (save_schedule_settings(), close_dialog(settings_dialog))),
        ],
    )

    # ── About Dialog ───────────────────────────────────────────

    about_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("About", color=TEXT_PRIMARY, weight=ft.FontWeight.W_700),
        bgcolor=BG_CARD,
        content=ft.Column([
            ft.Text("vChronos v1.0\nvMix Automation Scheduler\n\n" \
            "Author: Federico Guzman (https://github.com/kraiosis)\n\n" \
            "GitHub: https://github.com/kraiosis/vChronos"),
        ], spacing=12, tight=True),
        actions=[
            ft.Button("Close", bgcolor=ACCENT_BLUE, color="white",
                              on_click=lambda e: (close_dialog(about_dialog))),
        ],
    )

    # ── Helpers ────────────────────────────────────────────────────────────

    def close_dialog(dlg):
        dlg.open = False
        page.update()

    def open_dialog(dlg):
        page.overlay.clear()
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    def open_connection_dialog(e):
        conn_status_text.value = ""
        open_dialog(conn_dialog)

    def open_new_event_dialog(e):
        selected_event_id[0] = None
        ev = ScheduleEvent(
            name="New Event",
            event_type=EventType.VIDEO,
            trigger_type=TriggerType.TIME,
            transition=TransitionType.CUT,
            transition_duration_ms=1000,
            scheduled_time=datetime.now().strftime("%H:%M:%S"),
        )
        # Temporarily add for editing
        schedule.add_event(ev)
        selected_event_id[0] = ev.id
        populate_edit_dialog(ev)
        open_dialog(edit_dialog)

    def open_edit_event_dialog(event_id: str):
        ev = schedule.get_event(event_id)
        if not ev:
            return
        selected_event_id[0] = event_id
        populate_edit_dialog(ev)
        open_dialog(edit_dialog)

    def delete_event(event_id: str):
        schedule.remove_event(event_id)
        rebuild_event_list()
        log.info("Event deleted")

    def fire_event_now(event_id: str):
        engine.fire_event_now(event_id)

    def duplicate_event(event_id: str):
        import copy, uuid as _uuid
        ev = schedule.get_event(event_id)
        if ev:
            ev2 = copy.deepcopy(ev)
            ev2.id = str(_uuid.uuid4())
            ev2.name = ev.name + " (copy)"
            ev2.status = EventStatus.PENDING
            schedule.add_event(ev2)
            rebuild_event_list()

    # ── Event List Builder ─────────────────────────────────────────────────

    def build_event_row(ev: ScheduleEvent) -> ft.Container:
        status_col = STATUS_COLORS.get(ev.status, TEXT_DIM)
        status_icon = STATUS_ICONS.get(ev.status, ft.Icons.SCHEDULE)
        ev_color = ev.color or EVENT_COLORS.get(ev.event_type, ACCENT_BLUE)
        is_running = ev.status == EventStatus.RUNNING

        time_str = ev.scheduled_time or "—"
        trigger_label = {
            TriggerType.TIME: "⏰",
            TriggerType.CUE: "▶",
            TriggerType.TIME_OR_CUE: "⏰▶",
            TriggerType.MANUAL: "✋",
        }.get(ev.trigger_type, "")

        input_str = f"Input {ev.input_number}" if ev.input_number else (ev.input_name or "—")
        dur_str = f"{ev.duration_seconds}s" if ev.duration_seconds else ""

        row = ft.Container(
            content=ft.Row([
                # Color bar
                ft.Container(width=4, height=54, bgcolor=ev_color,
                             border_radius=ft.BorderRadius.only(top_left=4, bottom_left=4)),
                # Status icon
                ft.Container(
                    ft.Icon(status_icon, size=16, color=status_col),
                    width=28, 
                    # alignment=ft.alignment.center
                ),
                # Time + trigger
                ft.Container(
                    ft.Column([
                        ft.Text(time_str, size=13, weight=ft.FontWeight.W_700,
                                color=TEXT_PRIMARY, font_family="mono"),
                        ft.Text(trigger_label, size=10, color=TEXT_DIM),
                    ], spacing=0, tight=True),
                    width=68,
                ),
                # Event info
                ft.Column([
                    ft.Text(ev.name, size=13, weight=ft.FontWeight.W_600,
                            color=TEXT_PRIMARY if ev.enabled else TEXT_DIM,
                            overflow=ft.TextOverflow.ELLIPSIS, max_lines=1),
                    ft.Row([
                        ft.Container(
                            ft.Text(ev.event_type.value, size=10, color=ev_color),
                            bgcolor=ev_color + "22",
                            padding=ft.Padding.symmetric(horizontal=5, vertical=2),
                            border_radius=3,
                        ),
                        ft.Text(input_str, size=11, color=TEXT_SECONDARY),
                        ft.Text(dur_str, size=11, color=TEXT_DIM) if dur_str else ft.Text(""),
                    ], spacing=6),
                ], spacing=2, expand=True),
                # Action buttons
                ft.Row([
                    ft.IconButton(ft.Icons.PLAY_ARROW, icon_size=16,
                                  icon_color=ACCENT_GREEN,
                                  tooltip="Fire Now",
                                  on_click=lambda e, eid=ev.id: fire_event_now(eid)),
                    ft.IconButton(ft.Icons.EDIT_OUTLINED, icon_size=16,
                                  icon_color=ACCENT_CYAN,
                                  tooltip="Edit",
                                  on_click=lambda e, eid=ev.id: open_edit_event_dialog(eid)),
                    ft.IconButton(ft.Icons.COPY_OUTLINED, icon_size=16,
                                  icon_color=TEXT_SECONDARY,
                                  tooltip="Duplicate",
                                  on_click=lambda e, eid=ev.id: duplicate_event(eid)),
                    ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=16,
                                  icon_color=ACCENT_RED,
                                  tooltip="Delete",
                                  on_click=lambda e, eid=ev.id: (delete_event(eid), page.update())),
                ], spacing=0),
            ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=BG_ELEVATED if is_running else BG_SURFACE,
            border=ft.Border.all(1, ACCENT_CYAN if is_running else BORDER),
            border_radius=6,
            animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
            padding=ft.Padding.only(right=8),
            opacity=1.0 if ev.enabled else 0.55,
        )
        return row

    def rebuild_event_list():
        event_list_col.controls.clear()
        events = schedule.get_events_sorted()
        if not events:
            event_list_col.controls.append(
                ft.Container(
                    ft.Column([
                        ft.Icon(ft.Icons.PLAYLIST_ADD, size=40, color=TEXT_DIM),
                        ft.Text("No events yet", size=14, color=TEXT_DIM),
                        ft.Text("Click + Add Event to get started", size=12, color=TEXT_DIM),
                    ], 
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                    # alignment=ft.alignment.center,
                    height=200,
                )
            )
        else:
            for ev in events:
                event_list_col.controls.append(build_event_row(ev))
        try:
            page.update()
        except Exception:
            pass

    # ── Log Panel Builder ──────────────────────────────────────────────────

    def rebuild_log():
        entries = log.get_recent(60)
        log_col.controls.clear()
        for entry in reversed(entries):
            col = LOG_COLORS.get(entry.level, TEXT_SECONDARY)
            icon = {
                "info": "ℹ", "warning": "⚠", "error": "✗", "success": "✓"
            }.get(entry.level, "·")
            log_col.controls.append(
                ft.Row([
                    ft.Text(entry.timestamp, size=10, color=TEXT_DIM,
                            font_family="mono", width=54),
                    ft.Text(icon, size=11, color=col, width=14),
                    ft.Text(entry.message, size=11, color=col, expand=True,
                            overflow=ft.TextOverflow.ELLIPSIS),
                ], spacing=6)
            )
        try:
            page.update()
        except Exception:
            pass

    log.add_callback(lambda e: rebuild_log())

    # ── Engine Callbacks ───────────────────────────────────────────────────

    def on_event_started(ev: ScheduleEvent):
        rebuild_event_list()
        now_playing_text.value = ev.name
        now_status_text.value = f"{ev.event_type.value} · {ev.transition.value}"
        try:
            page.update()
        except Exception:
            pass

    def on_event_completed(ev: ScheduleEvent):
        rebuild_event_list()
        try:
            page.update()
        except Exception:
            pass

    def on_status_changed():
        if len(schedule.events) == 0:
            now_status_text.value = "No events scheduled"
            log.info(now_status_text.value)
        is_run = engine.is_running
        is_pause = engine.is_paused
        run_btn.disabled = is_run
        run_btn.content = "⏺ STARTED" if (is_run or is_pause) else "▶  START"
        # print(f"Status changed: is_running={is_run}, is_paused={is_pause}")
        # pause_btn.text = "▶  RESUME" if is_pause else "⏸  PAUSE"
        # pause_btn.bgcolor = ACCENT_GREEN if is_pause else ACCENT_AMBER
        pause_btn.content = "▶ RESUME" if is_pause else "⏸  PAUSE"
        pause_btn.disabled = False #not is_run
        stop_btn.disabled = not (is_run or is_pause)
        try:
            page.update()
        except Exception:
            pass

    def on_tick():
        now = datetime.now()
        clock_text.value = now.strftime("%H:%M:%S")
        # Next event countdown
        nxt = engine.get_next_event()
        if nxt:
            next_event_text.value = nxt.name
            td = engine.get_time_until_next()
            if td:
                total = int(td.total_seconds())
                h, rem = divmod(total, 3600)
                m, s = divmod(rem, 60)
                countdown_text.value = f"{h:02d}:{m:02d}:{s:02d}"
            else:
                countdown_text.value = "—"
        else:
            next_event_text.value = "—"
            countdown_text.value = "—"
            if not engine.is_running:
                now_playing_text.value = "—"
                now_status_text.value = "Idle"
        try:
            page.update()
        except Exception:
            pass

    def on_vmix_state(state):
        if state.connected:
            vmix_status_dot.bgcolor = ACCENT_GREEN
            vmix_status_dot.tooltip = f"vMix {state.version}"
            vmix_status_text.value = f"vMix {state.version}"
            vmix_status_text.color = ACCENT_GREEN
            # Active/preview
            active_name = "—"
            preview_name = "—"
            for inp in state.inputs:
                if inp.number == state.active_input:
                    active_name = f"#{inp.number} {inp.title}"
                if inp.number == state.preview_input:
                    preview_name = f"#{inp.number} {inp.title}"
            vmix_active_text.value = active_name
            vmix_preview_text.value = preview_name
            vmix_rec_icon.color = ACCENT_RED if state.recording else TEXT_DIM
            vmix_stream_icon.color = ACCENT_GREEN if state.streaming else TEXT_DIM
        else:
            vmix_status_dot.bgcolor = ACCENT_RED
            vmix_status_dot.tooltip = "Disconnected"
            vmix_status_text.value = "Disconnected"
            vmix_status_text.color = ACCENT_RED
        try:
            page.update()
        except Exception:
            pass

    engine.on_event_started = on_event_started
    engine.on_event_completed = on_event_completed
    engine.on_status_changed = on_status_changed
    engine.on_tick = on_tick
    api.add_poll_callback(on_vmix_state)

    # ── Transport Controls ─────────────────────────────────────────────────

    def on_run(e):
        if len(schedule.events) == 0:
            now_status_text.value = "No events scheduled"
            log.info(now_status_text.value)
        else:
            engine.start()

    def on_pause(e):
        if engine.is_paused:
            engine.resume()
        else:
            engine.pause()

    def on_stop(e):
        engine.stop()
        rebuild_event_list()
        page.update()

    run_btn.on_click = on_run
    pause_btn.on_click = on_pause
    stop_btn.on_click = on_stop

    # ── File Menu Actions ──────────────────────────────────────────────────

    async def new_schedule(e=None):
        engine.stop()
        nonlocal schedule
        schedule = Schedule(name="New Schedule")
        engine.load_schedule(schedule)
        current_file_path[0] = None
        schedule_name_text.value = schedule.name
        rebuild_event_list()
        log.info("New schedule created")

    async def save_schedule(e=None):
        fp = current_file_path[0]
        if fp:
            schedule.save(fp)
            log.success(f"Saved: {fp}")
        else:
            await save_schedule_as()

    async def save_schedule_as(e=None):
        # def on_result(ev: ft.FilePickerResultEvent):
        #     if ev.path:
        #         fp = ev.path if ev.path.endswith(".json") else ev.path + ".json"
        #         schedule.save(fp)
        #         current_file_path[0] = fp
        #         log.success(f"Saved: {fp}")
        picker = ft.FilePicker()
        # picker.on_result = on_result
        # page.overlay.append(picker)
        # page.update()
        path = await picker.save_file(
            dialog_title="Save Schedule",
            file_name=f"{schedule.name}.json",
            allowed_extensions=["json"],
        )
        if path:
                fp = path if path.endswith(".json") else path + ".json"
                schedule.save(fp)
                current_file_path[0] = fp
                log.success(f"Saved: {fp}")

    async def open_schedule_file(e=None):
        """
        Async Methods: Methods like pick_files(), save_file(), and get_directory_path() are now asynchronous 
        and return the result directly rather than triggering an on_result event.
        Platform Specifics: Note that while pick_files() works on the web, save_file() and get_directory_path() 
        are currently restricted to desktop platforms (Linux, macOS, Windows)
        """
        # def on_result(ev: ft.FilePickerResultEvent):
        #     if ev.files:
        #         fp = ev.files[0].path
        #         try:
        #             nonlocal schedule
        #             schedule = Schedule.load(fp)
        #             engine.load_schedule(schedule)
        #             current_file_path[0] = fp
        #             schedule_name_text.value = schedule.name
        #             rebuild_event_list()
        #             log.success(f"Opened: {fp}")
        #             if schedule.auto_run:
        #                 engine.start()
        #         except Exception as ex:
        #             log.error(f"Failed to open: {ex}")
        picker = ft.FilePicker()
        # picker.on_result = on_result
        # page.overlay.append(picker)
        # page.update()
        files = await picker.pick_files(
            dialog_title="Open Schedule",
            allowed_extensions=["json"],
            allow_multiple=False,
        )
        if files:
            fp = files[0].path
            try:
                nonlocal schedule
                schedule = Schedule.load(fp)
                engine.load_schedule(schedule)
                current_file_path[0] = fp
                schedule_name_text.value = schedule.name
                rebuild_event_list()
                log.success(f"Opened: {fp}")
                if schedule.auto_run:
                    engine.start()
            except Exception as ex:
                log.error(f"Failed to open: {ex}")
        else:
            print("Cancelled")

    def open_about(e):

        open_dialog(about_dialog)

    def open_settings(e):
        sched_name_field.value = schedule.name
        sched_desc_field.value = schedule.description
        sched_loop_switch.value = schedule.loop_schedule
        sched_autorun_switch.value = schedule.auto_run
        open_dialog(settings_dialog)

    async def exit_app(e):
        await page.window.close()

    # ── Layout ─────────────────────────────────────────────────────────────

    def stat_card(label, value_ctrl, icon=None, accent=None):
        return ft.Container(
            ft.Column([
                ft.Row([
                    ft.Icon(icon, size=13, color=accent or TEXT_DIM) if icon else ft.Text(""),
                    ft.Text(label, size=10, color=TEXT_DIM),
                ], spacing=4),
                value_ctrl,
            ], spacing=4, tight=True),
            bgcolor=BG_ELEVATED,
            border=ft.border.all(1, BORDER),
            border_radius=6,
            padding=10,
            expand=True,
        )

    header = ft.Container(
        ft.Row([
            # Logo area
            ft.Row([
                ft.Container(
                    ft.Image(
                        src="assets/favicon.png",
                        width=50,
                        height=50,
                    ),
                    # ft.Text("vChronos", size=13, weight=ft.FontWeight.W_900,
                    #          color=ACCENT_CYAN, font_family="mono"),
                    # bgcolor=ACCENT_CYAN + "18",
                    # padding=ft.padding.symmetric(horizontal=8, vertical=4),
                    # border_radius=4,
                    # border=ft.border.all(1, ACCENT_CYAN + "44"),
                ),
                ft.Column([
                    ft.Text("vMix Automation Scheduler", size=14,
                             weight=ft.FontWeight.W_700, color=TEXT_PRIMARY),
                    schedule_name_text,
                ], spacing=0, tight=True),
            ], spacing=10),

            ft.Row(expand=True),

            # Clock
            ft.Container(
                ft.Row([
                    ft.Icon(ft.Icons.SCHEDULE, size=14, color=ACCENT_CYAN),
                    clock_text,
                ], spacing=6),
                bgcolor=BG_ELEVATED,
                border=ft.Border.all(1, BORDER),
                border_radius=6, padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            ),

            # Transport
            ft.Row([run_btn, pause_btn, stop_btn], spacing=8),

            # Connection
            ft.Container(
                ft.Row([
                    vmix_status_dot,
                    vmix_status_text,
                    ft.IconButton(ft.Icons.SETTINGS_ETHERNET, icon_size=16,
                                  icon_color=TEXT_SECONDARY,
                                  tooltip="Configure vMix Connection",
                                  on_click=open_connection_dialog),
                ], spacing=6),
                bgcolor=BG_ELEVATED,
                border=ft.Border.all(1, BORDER),
                border_radius=6, padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            ),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
        bgcolor=BG_CARD,
        border=ft.Border.only(bottom=ft.border.BorderSide(1, BORDER)),
        padding=ft.Padding.symmetric(horizontal=20, vertical=10),
    )

    # Menu bar
    menubar = ft.Container(
        ft.Row([
            ft.TextButton("New", on_click=new_schedule,
                          style=ft.ButtonStyle(color=TEXT_SECONDARY)),
            ft.TextButton("Open", on_click=open_schedule_file,
                          style=ft.ButtonStyle(color=TEXT_SECONDARY)),
            ft.TextButton("Save", on_click=save_schedule,
                          style=ft.ButtonStyle(color=TEXT_SECONDARY)),
            ft.TextButton("Save As", on_click=save_schedule_as,
                          style=ft.ButtonStyle(color=TEXT_SECONDARY)),
            ft.Container(width=1, height=20, bgcolor=BORDER),
            ft.TextButton("Settings", on_click=open_settings,
                          style=ft.ButtonStyle(color=TEXT_SECONDARY)),
            ft.Container(width=1, height=20, bgcolor=BORDER),
            ft.TextButton("About", on_click=open_about,
                          style=ft.ButtonStyle(color=TEXT_SECONDARY)),
            ft.Container(width=1, height=20, bgcolor=BORDER),
            ft.TextButton("Exit", on_click=exit_app,
                          style=ft.ButtonStyle(color=TEXT_SECONDARY)),
        ], spacing=0),
        bgcolor=BG_CARD,
        border=ft.Border.only(bottom=ft.border.BorderSide(1, BORDER)),
        padding=ft.Padding.symmetric(horizontal=12, vertical=2),
    )

    # Event list panel
    event_panel = ft.Container(
        ft.Column([
            ft.Row([
                ft.Text("SCHEDULE", size=11, weight=ft.FontWeight.W_700,
                         color=TEXT_DIM, style=ft.TextStyle(letter_spacing=2, size=20)),
                ft.Row(expand=True),
                ft.IconButton(
                    ft.Icons.REFRESH, icon_size=16, icon_color=TEXT_SECONDARY,
                    tooltip="Reset all statuses",
                    on_click=lambda e: (schedule.reset_all_statuses(), rebuild_event_list()),
                ),
                ft.Button(
                    "+ Add Event", bgcolor=ACCENT_BLUE, color="white",
                    height=30,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=4)),
                    on_click=open_new_event_dialog,
                ),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(height=1, color=BORDER),
            event_list_col,
        ], spacing=8),
        bgcolor=BG_CARD,
        border=ft.Border.all(1, BORDER),
        border_radius=8,
        padding=12,
        expand=True,
    )

    # Status panel
    status_panel = ft.Container(
        ft.Column([
            ft.Text("NOW PLAYING", size=10, weight=ft.FontWeight.W_700,
                     color=TEXT_DIM, style=ft.TextStyle(letter_spacing=2, size=20)),
            ft.Divider(height=1, color=BORDER),
            ft.Column([
                now_playing_text,
                now_status_text,
            ], spacing=2),
            ft.Container(height=8),
            ft.Text("NEXT EVENT", size=10, color=TEXT_DIM, style=ft.TextStyle(letter_spacing=2, size=20)),
            next_event_text,
            ft.Text("Countdown", size=10, color=TEXT_DIM),
            countdown_text,
            ft.Container(height=8),
            ft.Divider(height=1, color=BORDER),
            ft.Text("vMIX STATE", size=10, color=TEXT_DIM, style=ft.TextStyle(letter_spacing=2, size=20)),
            ft.Row([
                ft.Text("Active:", size=11, color=TEXT_DIM, width=50),
                vmix_active_text,
            ]),
            ft.Row([
                ft.Text("Preview:", size=11, color=TEXT_DIM, width=50),
                vmix_preview_text,
            ]),
            ft.Row([
                ft.Icon(ft.Icons.FIBER_MANUAL_RECORD, size=10, color=ACCENT_RED),
                ft.Text("REC", size=10, color=TEXT_SECONDARY),
                vmix_rec_icon,
                ft.Text("REC", size=10, color=TEXT_DIM),
                ft.Container(width=8),
                ft.Icon(ft.Icons.WIFI_TETHERING, size=10, color=ACCENT_GREEN),
                vmix_stream_icon,
                ft.Text("STREAM", size=10, color=TEXT_DIM),
            ], spacing=4),
        ], spacing=6),
        bgcolor=BG_CARD,
        border=ft.Border.all(1, BORDER),
        border_radius=8,
        padding=14,
        width=200,
    )

    # Log panel
    log_panel = ft.Container(
        ft.Column([
            ft.Row([
                ft.Text("EVENT LOG", size=10, weight=ft.FontWeight.W_700,
                         color=TEXT_DIM, style=ft.TextStyle(letter_spacing=2, size=20)),
                ft.Row(expand=True),
                ft.IconButton(ft.Icons.DELETE_SWEEP, icon_size=14,
                              icon_color=TEXT_DIM,
                              tooltip="Clear log",
                              on_click=lambda e: (log.clear(), rebuild_log())),
            ]),
            ft.Divider(height=1, color=BORDER),
            ft.Container(log_col, expand=True),
        ], spacing=6),
        bgcolor=BG_CARD,
        border=ft.Border.all(1, BORDER),
        border_radius=8,
        padding=12,
        height=180,
    )

    # Main layout
    main_content = ft.Column([
        ft.Row([
            ft.Column([event_panel], expand=True, spacing=0),
            status_panel,
        ], spacing=10, expand=True, vertical_alignment=ft.CrossAxisAlignment.START),
        log_panel,
    ], spacing=10, expand=True)

    page.add(
        ft.Column([
            header,
            menubar,
            ft.Container(main_content, padding=12, expand=True),
        ], spacing=0, expand=True)
    )

    # ── Initial setup ──────────────────────────────────────────────────────
    rebuild_event_list()
    rebuild_log()
    log.info("vChronos v1.0 - vMix Automation Scheduler started")
    log.info("Connect to vMix using the ⚡ button in the toolbar")

    # Try auto-connect to localhost
    def try_autoconnect():
        import time as _time
        _time.sleep(1)
        ok, msg = api.test_connection()
        if ok:
            api.start_polling(interval=1.5)
            log.success(f"Auto-connected: {msg}")
        else:
            log.warning("vMix not found on localhost:8088 — use Connect to configure")

    threading.Thread(target=try_autoconnect, daemon=True).start()
    engine.on_tick = on_tick

if __name__ == "__main__":
    # ft.app(target=main, assets_dir="assets")
    ft.run(main, assets_dir="assets")
