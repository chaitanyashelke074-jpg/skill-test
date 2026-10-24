"""
led_switch - turn the ESP32 light on or off by voice.

Chain:  you say "turn on the light"  ->  the model calls this tool with action=on
        ->  this plugin sends the text ON over a Bluetooth serial (COM) port
        ->  the ESP32 (firmware: ultron_light.ino) switches the relay and answers STATE ON.

SETUP (one time)
    1. Flash ultron_light.ino to the ESP32 (it appears as a Bluetooth device ULTRON-LIGHT).
    2. Pair it in Windows, then look up its OUTGOING COM port
       (Bluetooth settings > More Bluetooth settings > COM Ports), for example COM5.
    3. pip install pyserial
    4. In the plugin settings enter that COM port and press TEST.

Only the words ON, OFF, TOGGLE and STATUS are ever sent. The plugin writes no files and
makes no network connections.
"""
from __future__ import annotations

import re
import time

from memory.config_manager import get_plugin_setting

_NS = "led_switch"
_BAUD = 9600
_PORT_RE = re.compile(r"^(COM\d{1,3}|/dev/[\w./-]+)$", re.I)

_ALIASES = {
    "on": "ON", "turn_on": "ON", "turn on": "ON", "enable": "ON", "1": "ON", "true": "ON",
    "off": "OFF", "turn_off": "OFF", "turn off": "OFF", "disable": "OFF", "0": "OFF",
    "false": "OFF",
    "toggle": "TOGGLE", "switch": "TOGGLE", "flip": "TOGGLE",
    "status": "STATUS", "state": "STATUS", "check": "STATUS",
}


class _Problem(Exception):
    """A failure whose message is safe and useful to speak aloud."""


def _port(values: dict | None = None) -> str:
    raw = values.get("port") if values is not None else get_plugin_setting(_NS, "port")
    port = str(raw or "").strip()
    if not _PORT_RE.match(port):
        raise _Problem("Sir, set the light's Bluetooth COM port in the plugin settings "
                       "first, for example COM5.")
    return port.upper() if port.upper().startswith("COM") else port


def _send(port: str, word: str) -> str:
    try:
        import serial
    except ImportError:
        raise _Problem("Sir, I need the pyserial package for that. Run: pip install pyserial")
    last = "no answer"
    for _attempt in (1, 2):
        try:
            with serial.Serial(port, _BAUD, timeout=3, write_timeout=3) as link:
                time.sleep(0.4)                       # let the Bluetooth link settle
                link.reset_input_buffer()
                link.write((word + "\n").encode("ascii"))
                link.flush()
                line = link.readline().decode("ascii", errors="replace").strip()
            if line:
                return line.upper()
        except serial.SerialException as e:
            last = str(e)
        time.sleep(1.0)
    raise _Problem(f"Sir, I could not reach the light switch ({last}). Is it powered, "
                   f"paired, and not connected to another app?")


def _sentence(reply: str, status_only: bool) -> str:
    if "STATE ON" in reply:
        return "Sir, the light is on." if not status_only else "The light is currently on."
    if "STATE OFF" in reply:
        return "Sir, the light is off." if not status_only else "The light is currently off."
    return "Sir, the light switch gave an answer I did not understand."


def _test(values: dict):
    """Settings-panel TEST button. Returns (ok, message)."""
    try:
        reply = _send(_port(values), "STATUS")
    except _Problem as e:
        return False, str(e).replace("Sir, ", "")
    return True, _sentence(reply, True)


PLUGIN = {
    "name": "led_switch",
    "description": (
        "Switches the user's ESP32 light (the LED strip on the relay) on or off over "
        "Bluetooth. Use when the user says things like turn on the light, turn off the "
        "lamp, switch the LED strip, toggle the light, or asks whether the light is on. "
        "action: on | off | toggle | status. It can only switch on and off; it cannot dim "
        "or change colour."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "on | off | toggle | status"},
        },
        "required": ["action"],
    },
}

PLUGIN_SETTINGS = {
    "namespace": _NS,
    "title": "LIGHT SWITCH",
    "fields": [
        {"key": "port", "type": "text", "label": "Bluetooth COM port",
         "placeholder": "COM5"},
    ],
    "action": {"label": "TEST", "run": _test},
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    word = _ALIASES.get(str(parameters.get("action", "")).strip().lower())
    if word is None:
        return "Sir, tell me whether to turn the light on, off, toggle it, or check it."
    try:
        return _sentence(_send(_port(), word), word == "STATUS")
    except _Problem as e:
        return str(e)
    except Exception as e:
        return f"Sir, the light switch failed: {e}"
