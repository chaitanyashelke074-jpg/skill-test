"""
blynk_light - turn the ESP32 light on or off by voice, through the Blynk cloud.

Chain:  you say "turn on the light"  ->  the model calls this tool with action=on
        ->  this plugin sends a web request to Blynk (https://blynk.cloud)
        ->  Blynk pushes the new value to the ESP32 (firmware: ultron_light_blynk.ino)
        ->  the ESP32 switches the relay.

NEEDS: Wi-Fi + internet on both the PC and the ESP32 (this is the Blynk cloud route).
Standard library only - no extra pip packages.

SETUP (one time)
    1. In Blynk: make a template with datastream V0 (Integer, 0 to 1) and add a device.
    2. Flash ultron_light_blynk.ino to the ESP32 (template ID, token, Wi-Fi inside it).
    3. In the plugin settings paste the device AUTH TOKEN, and press TEST.

SAFETY
    * The token works like a password: anyone who has it can switch your light. It is
      kept in the settings, never in this file.
    * The token is only ever sent to a blynk.cloud address (the server field is checked).
    * Only the values 0 and 1 are ever written, and only to datastream V0.
"""
from __future__ import annotations

import re
import time
import urllib.error
import urllib.parse
import urllib.request

from memory.config_manager import get_plugin_setting

_NS = "blynk_light"
_PIN = "V0"
_TIMEOUT = 10
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,64}$")
_HOST_RE = re.compile(r"^([a-z0-9-]{1,20}\.)?blynk\.cloud$")

_ALIASES = {
    "on": "ON", "turn_on": "ON", "turn on": "ON", "enable": "ON", "1": "ON", "true": "ON",
    "off": "OFF", "turn_off": "OFF", "turn off": "OFF", "disable": "OFF", "0": "OFF",
    "false": "OFF",
    "toggle": "TOGGLE", "switch": "TOGGLE", "flip": "TOGGLE",
    "status": "STATUS", "state": "STATUS", "check": "STATUS",
}


class _Problem(Exception):
    """A failure whose message is safe and useful to speak aloud (never contains the token)."""


def _settings(values: dict | None = None) -> tuple[str, str]:
    get = (lambda k: values.get(k)) if values is not None else (lambda k: get_plugin_setting(_NS, k))
    token = str(get("token") or "").strip()
    host = str(get("server") or "").strip().lower() or "blynk.cloud"
    host = re.sub(r"^https?://", "", host).strip("/")
    if not _TOKEN_RE.match(token):
        raise _Problem("Sir, paste your Blynk device token in the plugin settings first.")
    if not _HOST_RE.match(host):
        raise _Problem("Sir, the Blynk server must look like blynk.cloud or fra1.blynk.cloud.")
    return token, host


def _call(host: str, token: str, endpoint: str, pin_part: str | None = None) -> str:
    query = urllib.parse.urlencode({"token": token})
    if pin_part:
        query += "&" + pin_part
    url = f"https://{host}/external/api/{endpoint}?{query}"
    last = "no answer"
    for _attempt in (1, 2):
        try:
            with urllib.request.urlopen(url, timeout=_TIMEOUT) as resp:
                return resp.read().decode("utf-8", errors="replace").strip()
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403, 404):
                raise _Problem("Sir, Blynk rejected the request. Check the token and that "
                               f"datastream {_PIN} exists in your template.")
            last = f"Blynk error {e.code}"
        except (urllib.error.URLError, OSError):
            last = "I could not reach Blynk, so check the internet connection"
        time.sleep(1.0)
    raise _Problem(f"Sir, {last}.")


def _online(host: str, token: str) -> None:
    if _call(host, token, "isHardwareConnected").lower() != "true":
        raise _Problem("Sir, the light controller is offline. Check that it has power "
                       "and Wi-Fi.")


def _read(host: str, token: str) -> bool:
    return _call(host, token, "get", _PIN).strip("[]\" ") == "1"


def _write(host: str, token: str, on: bool) -> None:
    _call(host, token, "update", f"{_PIN}={1 if on else 0}")


def _sentence(on: bool, status_only: bool) -> str:
    if status_only:
        return "The light is currently on." if on else "The light is currently off."
    return "Sir, the light is on." if on else "Sir, the light is off."


def _test(values: dict):
    """Settings-panel TEST button. Returns (ok, message)."""
    try:
        token, host = _settings(values)
        _online(host, token)
        return True, "The controller is online. " + _sentence(_read(host, token), True)
    except _Problem as e:
        return False, str(e).replace("Sir, ", "")


PLUGIN = {
    "name": "blynk_light",
    "description": (
        "Switches the user's room light (the ESP32 LED strip on a relay) on or off through "
        "the Blynk cloud. Use when the user says things like turn on the light, turn off "
        "the lamp, switch the LED strip, toggle the light, or asks whether the light is on. "
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
    "title": "LIGHT SWITCH (BLYNK)",
    "fields": [
        {"key": "token", "type": "password", "label": "Blynk device token",
         "placeholder": "paste the Auth Token"},
        {"key": "server", "type": "text", "label": "Blynk server",
         "placeholder": "blynk.cloud (or fra1.blynk.cloud, blr1.blynk.cloud ...)"},
    ],
    "action": {"label": "TEST", "run": _test},
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    word = _ALIASES.get(str(parameters.get("action", "")).strip().lower())
    if word is None:
        return "Sir, tell me whether to turn the light on, off, toggle it, or check it."
    try:
        token, host = _settings()
        _online(host, token)
        if word == "STATUS":
            return _sentence(_read(host, token), True)
        target = (not _read(host, token)) if word == "TOGGLE" else (word == "ON")
        _write(host, token, target)
        return _sentence(target, False)
    except _Problem as e:
        return str(e)
    except Exception as e:
        return f"Sir, the light switch failed: {type(e).__name__}."
