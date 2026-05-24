# vChronos Automation Scheduler

A professional automation scheduler for vMix live streaming software — similar to vTask — built with Python and the Flet GUI framework.

![Alt Text](https://github.com/kraiosis/vChronos/blob/main/assets/vChronos_v1.0.png)
---

## Features

- **Time-based scheduling** — fire events at exact clock times (HH:MM:SS)
- **Cue-based scheduling** — fire events when the previous one ends
- **Both time + cue** — whichever comes first
- **All vMix content types supported:**
  - Videos / Clips
  - Titles / Lower Thirds (with dynamic field text)
  - Overlays / Graphics (channels 1–4, on/off/toggle)
  - Playlists (start, stop, next, previous)
  - Live Inputs
  - Raw vMix function commands
- **Transitions** — Cut, Fade, Zoom, Wipe, Slide, Fly, CrossZoom, Cube, Merge
- **Live vMix state monitor** — active input, preview, recording, streaming status
- **Event log** — real-time log of all scheduler actions
- **Fire events manually** at any time
- **Duplicate, edit, delete** events in the UI
- **Save/load schedules** as JSON files
- **Auto-connect** to vMix on localhost at startup
- **Network support** — connect to vMix on any IP address on your LAN

---

## Requirements

- Python 3.10 or newer
- Flet Framework 0.21.0 or newer
- vMix (any version with Web API enabled)
- Windows, macOS, or Linux
- Pyinstaller (optional)

---

## Installation

```bash
# 1. Clone or unzip the project
cd vmix_scheduler

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run
python main.py

# 4. Compile (Optional - requires Pyinstaller)
flet pack main.py --icon assets/icon.ico
```

---

## Enable vMix Web API

1. Open vMix
2. Go to **Settings → Web Controller**
3. Enable **Web Controller**
4. Note the port (default: **8088**)
5. If running on a different machine, note the IP address

---

## Project Structure

```
vmix_scheduler/
├── main.py                  # Flet UI application (entry point)
├── requirements.txt
├── README.md
└── core/
    ├── __init__.py
    ├── vmix_api.py          # vMix HTTP API client
    ├── models.py            # Schedule/Event data models + EventLog
    └── scheduler.py         # Scheduling engine (time + cue logic)
```

---

## How to Use

### 1. Connect to vMix
Click the **⚡ network icon** in the top-right toolbar. Enter your vMix host (IP or `localhost`) and port (default `8088`). Click **Test & Connect**.

The status indicator turns green when connected.

### 2. Create Events
Click **+ Add Event**. Fill in:

| Field | Description |
|-------|-------------|
| Event Name | A label for this block |
| Event Type | Video, Title, Overlay, Playlist, Live Input, or Command |
| Input Number | The vMix input number to use |
| Scheduled Time | HH:MM:SS when to fire |
| Trigger | Time / Cue / Both / Manual |
| Transition | Cut, Fade, Wipe, etc. |
| Transition Duration | Milliseconds (e.g. 1000 = 1 second) |
| Event Duration | Seconds — used for cue-based next trigger |
| Title Fields | For Title events: field name + text value pairs |
| Overlay Channel | 1–4 overlay channel |
| Overlay Action | on / off / toggle |
| Playlist Action | start / stop / next / previous |

### 3. Start the Scheduler
Click **▶ START**. The engine begins polling the schedule. Events fire automatically based on their trigger settings.

Use **⏸ PAUSE** to temporarily halt and **⏹ STOP** to reset.

### 4. Manual Fire
Each event has a **▶ green play button** — click it to fire the event immediately at any time, regardless of the schedule.

### 5. Save / Load Schedules
Use the menu bar: **Save / Save As / Open**. Schedules are stored as `.json` files.

---

## Event Types Reference

### Video / Clip
Puts the input into preview, then transitions to program.

### Title / Lower Third
Sets title field text values first, then transitions to program. Add as many field/value pairs as needed.

### Overlay / Graphic
Sends the input to an overlay channel (1–4). Actions: `on`, `off`, `toggle`.

### Playlist
Controls vMix's built-in playlist: `start`, `stop`, `next`, `previous`.

### Live Input
Same as Video — transitions a live camera or capture input to program.

### vMix Command
Send any raw vMix API function. Enter in the **Notes** field using this format:
```
FunctionName Param1=Value1 Param2=Value2
```
Example:
```
SetVolume Input=3 Value=50
StartRecording
FadeToBlack
```

---

## Trigger Types

| Trigger | Behavior |
|---------|----------|
| `time` | Fires at the exact scheduled clock time |
| `cue` | Fires when the previous event's duration expires |
| `time_or_cue` | Fires whichever comes first |
| `manual` | Only fires when you click the ▶ button |

---

## Schedule JSON Format

```json
{
  "name": "Morning Broadcast",
  "events": [
    {
      "name": "Intro Slate",
      "event_type": "Video/Clip",
      "input_number": 1,
      "scheduled_time": "08:00:00",
      "trigger_type": "time",
      "transition": "Fade",
      "transition_duration_ms": 1500,
      "duration_seconds": 30,
      "enabled": true
    }
  ]
}
```

---

## Tips

- Set **Event Duration** on Video events to enable cue-chaining — the next cue event fires automatically after that many seconds.
- Use **Overlay events** with `off` action and a `post_action_delay_ms` to auto-remove lower thirds after N milliseconds.
- Disable events without deleting them using the **Enabled** toggle in the event editor.
- Use **Days of Week** filtering (editable in JSON) to have certain events only run on specific days.
- The scheduler checks every 250ms, so timing accuracy is within ~250ms.

---

## vMix API Reference

This app uses the vMix Web API documented at:
[https://www.vmix.com/help26/WebAPIReference.html](https://www.vmix.com/help25/index.htm?DeveloperAPI.html)

All API calls are standard HTTP GET requests to `http://HOST:PORT/api?Function=...`
