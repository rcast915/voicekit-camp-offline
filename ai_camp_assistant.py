#!/usr/bin/env python3
"""
ai_camp_assistant.py  —  AI Summer Camp Voice Kit Application

A voice assistant for the Google AIY Voice Kit V1.  Students HOLD the button
while they talk; the recording is sent over the Ethernet cable to the
instructor's computer (computer/server.py), which runs speech-to-text and a
local AI model.  The reply comes back as text and the Pi speaks it.

Nothing goes to the internet.

Instructors paste student code into boot_sequence.py (the startup animation
and personality prompt).  The personality is sent to the computer at startup;
it can also be edited there at http://localhost:8000, along with the voice
the box speaks with.

Button:
    Hold and talk     ask a question
    3 quick clicks    reboot the Pi

Usage:
    python3 ai_camp_assistant.py
"""

# =========================================================================
#  IMPORTS
# =========================================================================
import base64
import json
import logging
import math
import signal
import socket
import struct
import subprocess
import sys
import time
import threading
import urllib.request
import urllib.error
import wave

import boot_sequence as boot_config  # alias avoids collision with boot_sequence() function

import RPi.GPIO as GPIO

from aiy.board import Board, Led
from aiy.voice import tts
from aiy.voice.audio import AudioFormat, play_wav, record_file


# =========================================================================
#  CONFIGURATION
# =========================================================================

# --- Hardware pin assignments (Voice HAT V1 servo header) ----------------
GREEN_LED_PIN = 26        # External green LED
RED_LED_PIN   = 6         # External red LED
BUTTON_PIN    = 23        # Built-in arcade button (read-only for rapid clicks)

# --- The instructor's computer running computer/server.py ----------------
SERVER_URL = "http://192.168.50.1:8000"
PI_NAME    = socket.gethostname()    # Picks prompts/<PI_NAME>.txt on the computer

# --- Recording -----------------------------------------------------------
RECORDING_FILE     = "/tmp/aiy_camp_question.wav"
REPLY_FILE         = "/tmp/aiy_camp_reply.wav"
RECORD_FORMAT      = AudioFormat(sample_rate_hz=16000, num_channels=1, bytes_per_sample=2)
MAX_RECORD_SECONDS = 15     # Recording stops here even if the button is still held
MIN_RECORD_SECONDS = 0.5    # Shorter presses are clicks (e.g. for reboot), not questions

# --- Rapid-click reboot --------------------------------------------------
REBOOT_CLICKS         = 3
REBOOT_WINDOW_SECONDS = 3.0

# --- Voice settings ------------------------------------------------------
VOICE_VOLUME = 85
VOICE_PITCH  = 105
VOICE_SPEED  = 90

# --- Musical note frequencies (matches Jupyter notebook) -----------------
NOTE_FREQS = {
    "C": 262, "C#": 277, "D": 294, "D#": 311, "E": 330,
    "F": 349, "F#": 370, "G": 392, "G#": 415, "A": 440,
    "A#": 466, "B": 494,
}

# --- Global state --------------------------------------------------------
system_prompt = ""      # Set by boot_sequence(), sent to the computer at startup
_board        = None    # Set by main() once Board() is initialised


# =========================================================================
#  HELPER FUNCTIONS  — same API as the Jupyter notebook
# =========================================================================

def Turn_On_LED(color):
    """Turn on an external LED by color name.

    Supported colours: 'red', 'green', 'off'.
    Maps to two physical LEDs on the Voice HAT servo header.
    """
    color = color.lower()
    if color == "green":
        GPIO.output(GREEN_LED_PIN, GPIO.HIGH)
        GPIO.output(RED_LED_PIN, GPIO.LOW)
    elif color == "red":
        GPIO.output(RED_LED_PIN, GPIO.HIGH)
        GPIO.output(GREEN_LED_PIN, GPIO.LOW)
    elif color == "off":
        GPIO.output(GREEN_LED_PIN, GPIO.LOW)
        GPIO.output(RED_LED_PIN, GPIO.LOW)
    else:
        logging.warning("Unknown LED color: '%s' — use 'red', 'green', or 'off'.", color)
    logging.debug("LED → %s", color)


def Set_Button_LED(effect, duration=None):
    """Control the Voice Kit button LED.  **Same API as the Jupyter notebook.**

    Supported effects: 'on', 'off', 'blink', 'breathe'.
    Optional *duration* in seconds — LED returns to OFF after that time.
    """
    if _board is None:
        logging.warning("Set_Button_LED called before Board is ready.")
        return

    effect_lower = effect.lower()
    _LED_MAP = {
        "on":      Led.ON,
        "off":     Led.OFF,
        "blink":   Led.BLINK,
        "breathe": Led.PULSE_SLOW,
    }

    state = _LED_MAP.get(effect_lower)
    if state is None:
        logging.warning("Unknown LED effect: '%s' — use 'on', 'off', 'blink', or 'breathe'.", effect)
        return

    _board.led.state = state
    logging.debug("Button LED → %s", effect_lower)

    if duration and effect_lower != "off":
        time.sleep(duration)
        _board.led.state = Led.OFF


def _play_single_freq(freq, duration):
    """Generate a sine-wave WAV file and play it through the Voice HAT speaker."""
    filename = "/tmp/aiy_camp_tone.wav"
    sample_rate = 22050
    n_samples = int(sample_rate * duration)

    with wave.open(filename, 'w') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        for i in range(n_samples):
            # Volume capped at 60 % to protect classroom ears
            value = int(32767.0 * 0.6 * math.sin(
                2.0 * math.pi * freq * i / sample_rate
            ))
            w.writeframesraw(struct.pack('<h', value))

    try:
        play_wav(filename)
    except Exception:
        # Fallback to raw aplay if play_wav fails
        subprocess.call(['aplay', '-q', filename])


def Play_Note(note, duration):
    """Play a musical note for *duration* seconds.

    Accepts single notes ('C', 'D#', 'A'), minor chord arpeggios
    ('Am', 'Dm', 'Gm'), and "" for a rest (silence).
    Matches the Jupyter notebook API.
    """
    note = note.strip().upper()
    logging.debug("Playing note %s for %.2fs", note or "(rest)", duration)
    try:
        if not note:
            time.sleep(duration)
        elif note.endswith("M"):
            # Minor chord arpeggios
            arpeggios = {
                "AM": [220, 262, 330], "BM": [247, 294, 370],
                "CM": [262, 311, 392], "DM": [294, 349, 440],
                "EM": [330, 392, 494], "FM": [349, 415, 523],
                "GM": [392, 466, 587],
            }
            freqs = arpeggios.get(note, [440])
            arp_dur = duration / len(freqs)
            for f in freqs:
                _play_single_freq(f, arp_dur)
        else:
            freq = NOTE_FREQS.get(note, 440)
            _play_single_freq(freq, duration)
    except Exception as e:
        logging.error("Play_Note error: %s", e)
        time.sleep(duration)


def say(text):
    """Speak *text* aloud through the Voice Kit speaker."""
    tts.say(text, volume=VOICE_VOLUME, pitch=VOICE_PITCH, speed=VOICE_SPEED)


def _speak_reply(text, audio_b64):
    """Play the reply in the voice picked on the computer, or the Pi's own voice."""
    if audio_b64:
        try:
            with open(REPLY_FILE, "wb") as f:
                f.write(base64.b64decode(audio_b64))
            try:
                play_wav(REPLY_FILE)
            except Exception:
                subprocess.check_call(['aplay', '-q', REPLY_FILE])
            return
        except Exception as e:
            logging.error("Could not play the computer's voice (%s) — using the Pi's.", e)
    say(text)


# =========================================================================
#  BOOT SEQUENCE  —  student code lives in boot_sequence.py
# =========================================================================

def boot_sequence():
    """Run the startup animation and pick up the student's personality prompt."""
    global system_prompt

    # Call the external file sequence and pass local helper functions as arguments
    system_prompt = boot_config.run_boot_sequence(
        set_led_func=Set_Button_LED,
        play_note_func=Play_Note,
        turn_on_led_func=Turn_On_LED,
        say_func=say,
    ) or ""


# =========================================================================
#  TALKING TO THE COMPUTER
# =========================================================================

def _post(path, body=b"", content_type="application/octet-stream", timeout=60):
    """POST to computer/server.py and return the decoded JSON reply."""
    req = urllib.request.Request(
        SERVER_URL + path,
        data=body,
        headers={"Content-Type": content_type, "X-Pi-Name": PI_NAME},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _wait_for_server():
    """Block until the computer answers (it may still be booting).

    Also clears this Pi's chat memory and sends the student's personality
    prompt (if boot_sequence.py set one).
    """
    body = json.dumps({"prompt": system_prompt}).encode("utf-8")
    announced = False
    while True:
        try:
            _post("/reset", body, "application/json", timeout=5)
            logging.info("Connected to %s as '%s'.", SERVER_URL, PI_NAME)
            return
        except (urllib.error.URLError, OSError, ValueError) as e:
            logging.warning("Server not reachable yet: %s", e)
            if not announced:
                say("Waiting for the computer.")
                announced = True
            time.sleep(3)


def _record_question(board):
    """Record while the button is held.  Returns how many seconds were recorded."""
    start = time.monotonic()
    record_file(
        RECORD_FORMAT,
        filename=RECORDING_FILE,
        filetype="wav",
        wait=lambda: board.button.wait_for_release(timeout=MAX_RECORD_SECONDS),
    )
    return time.monotonic() - start


def _ask_server():
    """Send the recording; returns {"heard", "command", "reply"}."""
    with open(RECORDING_FILE, "rb") as f:
        return _post("/ask", f.read(), "audio/wav")


# =========================================================================
#  SYSTEM COMMANDS
# =========================================================================

def _power_off():
    say("Goodbye!")
    subprocess.call("sudo shutdown now", shell=True)


def _reboot():
    say("Restarting! Give me a moment.")
    subprocess.call("sudo systemctl restart voicekit.service", shell=True)


def _say_ip():
    try:
        ip = subprocess.check_output(
            "hostname -I | cut -d' ' -f1", shell=True
        )
        say("My IP address is %s" % ip.decode("utf-8").strip())
    except Exception as e:
        logging.error("Could not get IP: %s", e)
        say("Sorry, I could not get the IP address.")


# =========================================================================
#  RAPID-CLICK REBOOT MONITOR
# =========================================================================

def _start_rapid_click_monitor():
    """Start a background thread that reboots the Pi after 3 quick clicks.

    An emergency reset so instructors don't have to pull the power cable.
    Requires REBOOT_CLICKS presses within REBOOT_WINDOW_SECONDS, so normal
    hold-to-talk use never triggers it.
    """

    def _monitor():
        click_times = []
        while True:
            try:
                # Wait for button press (active LOW on Voice Kit V1)
                while GPIO.input(BUTTON_PIN) != 0:
                    time.sleep(0.05)

                now = time.monotonic()
                # Record this click and discard old ones outside the window
                click_times.append(now)
                click_times = [t for t in click_times
                               if now - t <= REBOOT_WINDOW_SECONDS]
                logging.debug("Reboot clicks: %d/%d", len(click_times), REBOOT_CLICKS)

                if len(click_times) >= REBOOT_CLICKS:
                    logging.warning("RAPID CLICK DETECTED (%d clicks) — REBOOTING", REBOOT_CLICKS)
                    try:
                        tts.say("Rebooting now.", volume=60)
                    except Exception:
                        pass
                    time.sleep(0.4)
                    subprocess.call(["sudo", "reboot"])
                    return

                # Wait for button release before counting the next click
                while GPIO.input(BUTTON_PIN) == 0:
                    time.sleep(0.05)

            except Exception:
                # GPIO.input may fail briefly before Board initialises the pin.
                # Sleep and retry silently.
                time.sleep(1)

    thread = threading.Thread(target=_monitor, daemon=True, name="rapid-click")
    thread.start()
    logging.info("Rapid-click reboot monitor started (%d clicks in %.0fs to reboot).",
                 REBOOT_CLICKS, REBOOT_WINDOW_SECONDS)


# =========================================================================
#  MAIN
# =========================================================================

def main():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))

    # --- GPIO setup for external LEDs ------------------------------------
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(GREEN_LED_PIN, GPIO.OUT)
    GPIO.setup(RED_LED_PIN, GPIO.OUT)

    try:
        with Board() as board:
            # Make board available to Set_Button_LED and other helpers
            global _board
            _board = board

            # --- Boot sequence (LEDs + sounds + personality) -------------
            try:
                boot_sequence()
            except Exception as e:
                logging.error("Boot sequence error: %s", e)
                say("Boot error. Starting assistant anyway.")

            # --- Connect to the computer (sends the personality) ---------
            _wait_for_server()

            # Start rapid-click reboot monitor (after Board configures the button)
            _start_rapid_click_monitor()

            say("Ready!")

            while True:
                board.led.state = Led.PULSE_SLOW        # Idle — slow breathing
                logging.info("Hold the button and speak...")

                board.button.wait_for_press()
                board.led.state = Led.ON                # Listening — solid
                seconds = _record_question(board)

                if seconds < MIN_RECORD_SECONDS:
                    # A quick click (maybe one of the 3 reboot clicks), not a question
                    logging.debug("Ignored %.2fs click.", seconds)
                    continue

                board.led.state = Led.PULSE_QUICK       # Thinking — quick pulse
                Turn_On_LED("green")
                try:
                    result = _ask_server()
                except (urllib.error.URLError, OSError, ValueError) as e:
                    logging.error("Server error: %s", e)
                    say("I can't reach the computer.")
                    continue

                text = result.get("heard")
                if not text:
                    logging.info("Nothing heard.")
                    continue
                logging.info("Heard: '%s'", text)

                # --- System commands (recognised by the server) ---------
                command = result.get("command")
                if command == "power_off":
                    _power_off()

                elif command == "reboot":
                    _reboot()

                elif command == "ip_address":
                    _say_ip()

                elif command == "exit":
                    say("Goodbye!")
                    break

                # --- Conversation ---------------------------------------
                else:
                    reply = result.get("reply") or "Something went wrong."
                    print("You: %s" % text)
                    print("Bot: %s" % reply)
                    _speak_reply(reply, result.get("audio"))

    except KeyboardInterrupt:
        logging.info("Interrupted by user.")
    finally:
        Turn_On_LED("off")
        GPIO.cleanup()
        logging.info("GPIO cleaned up. Exiting.")


if __name__ == "__main__":
    main()
