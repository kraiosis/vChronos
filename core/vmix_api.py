"""
vMix API Client
Handles all HTTP communication with vMix via its Web API.
Supports both localhost and network connections.
"""

import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional
import threading
import time


@dataclass
class VMixInput:
    key: str
    number: int
    title: str
    input_type: str
    state: str = ""
    duration: int = 0
    position: int = 0
    loop: bool = False
    muted: bool = False


@dataclass
class VMixState:
    connected: bool = False
    version: str = ""
    inputs: list = field(default_factory=list)
    active_input: int = 0
    preview_input: int = 0
    recording: bool = False
    streaming: bool = False
    overlay_inputs: list = field(default_factory=list)
    fade_to_black: bool = False
    master_volume: float = 100.0
    error: str = ""


class VMixAPI:
    """Client for the vMix HTTP Web API."""

    TRANSITIONS = [
        "Cut", "Fade", "Zoom", "Wipe", "Slide", "Fly",
        "CrossZoom", "FlyRotate", "Cube", "CubeZoom",
        "VerticalWipe", "VerticalSlide", "Merge",
        "WipeReverse", "SlideReverse", "VerticalWipeReverse",
        "VerticalSlideReverse"
    ]

    OVERLAY_CHANNELS = [1, 2, 3, 4]

    def __init__(self, host: str = "localhost", port: int = 8088):
        self.host = host
        self.port = port
        self.timeout = 3
        self._state = VMixState()
        self._state_lock = threading.Lock()
        self._poll_thread: Optional[threading.Thread] = None
        self._polling = False
        self._poll_callbacks = []

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def _request(self, path: str, params: dict = None, timeout: int = None) -> Optional[str]:
        """Make an HTTP GET request to vMix."""
        url = f"{self.base_url}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(url, timeout=timeout or self.timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as e:
            return None
        except Exception:
            return None

    def test_connection(self) -> tuple[bool, str]:
        """Test connection to vMix. Returns (success, message)."""
        result = self._request("/api", timeout=3)
        if result is None:
            return False, f"Cannot connect to vMix at {self.host}:{self.port}"
        try:
            root = ET.fromstring(result)
            version = root.get("version", "unknown")
            return True, f"Connected to vMix {version}"
        except ET.ParseError:
            return False, "Invalid response from vMix"

    def get_full_state(self) -> VMixState:
        """Fetch and parse full vMix API state."""
        result = self._request("/api")
        state = VMixState()
        if result is None:
            state.connected = False
            state.error = f"Cannot reach vMix at {self.host}:{self.port}"
            return state

        try:
            root = ET.fromstring(result)
            state.connected = True
            state.version = root.get("version", "")

            # Active / Preview
            active_el = root.find("active")
            preview_el = root.find("preview")
            if active_el is not None:
                state.active_input = int(active_el.text or 0)
            if preview_el is not None:
                state.preview_input = int(preview_el.text or 0)

            # Recording / Streaming
            rec_el = root.find("recording")
            stream_el = root.find("streaming")
            state.recording = rec_el is not None and rec_el.text == "True"
            state.streaming = stream_el is not None and stream_el.text == "True"

            # FTB
            ftb_el = root.find("fadeToBlack")
            state.fade_to_black = ftb_el is not None and ftb_el.text == "True"

            # Inputs
            inputs_el = root.find("inputs")
            if inputs_el is not None:
                for inp in inputs_el.findall("input"):
                    vmix_inp = VMixInput(
                        key=inp.get("key", ""),
                        number=int(inp.get("number", 0)),
                        title=inp.get("title", ""),
                        input_type=inp.get("type", ""),
                        state=inp.get("state", ""),
                        duration=int(inp.get("duration", 0)),
                        position=int(inp.get("position", 0)),
                        loop=inp.get("loop", "False") == "True",
                        muted=inp.get("muted", "False") == "True",
                    )
                    state.inputs.append(vmix_inp)

            # Overlays
            overlays_el = root.find("overlays")
            if overlays_el is not None:
                for ov in overlays_el.findall("overlay"):
                    num = ov.get("number", "")
                    if ov.text:
                        state.overlay_inputs.append({"channel": num, "input": ov.text})

        except ET.ParseError as e:
            state.connected = False
            state.error = f"XML parse error: {e}"

        return state

    def send_function(self, function: str, **kwargs) -> bool:
        """Send a vMix API function call."""
        params = {"Function": function}
        params.update(kwargs)
        result = self._request("/api", params=params)
        return result is not None

    # ── Transition & Input Control ──────────────────────────────────────────

    def cut(self, input_num: int = None) -> bool:
        kwargs = {}
        if input_num:
            kwargs["Input"] = input_num
        return self.send_function("Cut", **kwargs)

    def fade(self, input_num: int = None, duration: int = 1000) -> bool:
        kwargs = {"Duration": duration}
        if input_num:
            kwargs["Input"] = input_num
        return self.send_function("Fade", **kwargs)

    def transition(self, transition_type: str, input_num: int = None, duration: int = 1000) -> bool:
        kwargs = {"Duration": duration}
        if input_num:
            kwargs["Input"] = input_num
        return self.send_function(transition_type, **kwargs)

    def set_preview(self, input_num: int) -> bool:
        return self.send_function("PreviewInput", Input=input_num)

    def play_input(self, input_num: int) -> bool:
        return self.send_function("Play", Input=input_num)

    def pause_input(self, input_num: int) -> bool:
        return self.send_function("Pause", Input=input_num)

    def restart_input(self, input_num: int) -> bool:
        return self.send_function("Restart", Input=input_num)

    def set_loop(self, input_num: int, loop: bool) -> bool:
        fn = "SetLoop" if loop else "SetNoLoop"
        return self.send_function(fn, Input=input_num)

    # ── Title / GT Control ──────────────────────────────────────────────────

    def set_title_text(self, input_num: int, field_name: str, value: str) -> bool:
        return self.send_function(
            "SetText", Input=input_num,
            SelectedName=field_name, Value=value
        )

    def set_title_image(self, input_num: int, field_name: str, value: str) -> bool:
        return self.send_function(
            "SetImage", Input=input_num,
            SelectedName=field_name, Value=value
        )

    def set_next_title(self, input_num: int) -> bool:
        return self.send_function("NextPage", Input=input_num)

    # ── Overlay Control ─────────────────────────────────────────────────────

    def overlay_input_on(self, channel: int, input_num: int) -> bool:
        return self.send_function(f"OverlayInput{channel}On", Input=input_num)

    def overlay_input_off(self, channel: int) -> bool:
        return self.send_function(f"OverlayInput{channel}Off")

    def overlay_input_toggle(self, channel: int, input_num: int) -> bool:
        return self.send_function(f"OverlayInput{channel}", Input=input_num)

    # ── Playlist Control ────────────────────────────────────────────────────

    def start_playlist(self) -> bool:
        return self.send_function("StartPlayList")

    def stop_playlist(self) -> bool:
        return self.send_function("StopPlayList")

    def next_playlist_item(self) -> bool:
        return self.send_function("NextPlayListItem")

    def previous_playlist_item(self) -> bool:
        return self.send_function("PreviousPlayListItem")

    # ── Volume ──────────────────────────────────────────────────────────────

    def set_volume(self, input_num: int, volume: int) -> bool:
        return self.send_function("SetVolume", Input=input_num, Value=volume)

    def set_master_volume(self, volume: int) -> bool:
        return self.send_function("SetMasterVolume", Value=volume)

    def mute(self, input_num: int) -> bool:
        return self.send_function("MuteInput", Input=input_num)

    def unmute(self, input_num: int) -> bool:
        return self.send_function("UnMuteInput", Input=input_num)

    # ── Recording / Streaming ───────────────────────────────────────────────

    def start_recording(self) -> bool:
        return self.send_function("StartRecording")

    def stop_recording(self) -> bool:
        return self.send_function("StopRecording")

    def start_streaming(self) -> bool:
        return self.send_function("StartStreaming")

    def stop_streaming(self) -> bool:
        return self.send_function("StopStreaming")

    # ── Fade to Black ───────────────────────────────────────────────────────

    def fade_to_black(self) -> bool:
        return self.send_function("FadeToBlack")

    # ── State Polling ───────────────────────────────────────────────────────

    def add_poll_callback(self, cb):
        self._poll_callbacks.append(cb)

    def remove_poll_callback(self, cb):
        self._poll_callbacks = [c for c in self._poll_callbacks if c != cb]

    def start_polling(self, interval: float = 1.0):
        """Start background polling of vMix state."""
        if self._polling:
            return
        self._polling = True

        def _poll():
            while self._polling:
                state = self.get_full_state()
                with self._state_lock:
                    self._state = state
                for cb in list(self._poll_callbacks):
                    try:
                        cb(state)
                    except Exception:
                        pass
                time.sleep(interval)

        self._poll_thread = threading.Thread(target=_poll, daemon=True)
        self._poll_thread.start()

    def stop_polling(self):
        self._polling = False

    def get_cached_state(self) -> VMixState:
        with self._state_lock:
            return self._state
