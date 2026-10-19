#!/usr/bin/env python3
"""
ai_camp_assistant.py  —  AI Summer Camp Voice Kit Application

A voice assistant for the Google AIY Voice Kit V1.  Students HOLD the button
while they talk; the recording is sent over the Ethernet cable to the
instructor's computer (computer/server.py), which runs speech-to-text and a
local AI model.  The reply comes back as text and the Pi speaks it.

Nothing goes to the internet.  The bot's personality is NOT in this file —
edit computer/prompts/default.txt (or computer/prompts/<this-pi's-hostname>.txt)
on the computer instead.

Instructors paste student code into boot_sequence() to customise the
startup animation.

Usage:
    python3 ai_camp_assistant.py
"""

# =========================================================================
#  IMPORTS
# =========================================================================
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
BUTTON_PIN    = 23        # Built-in arcade button (read-only for long press)

# --- The instructor's computer running computer/server.py ----------------
SERVER_URL = "http://192.168.50.1:8000"
PI_NAME    = socket.gethostname()    # Picks prompts/<PI_NAME>.txt if it exists

# --- Recording -----------------------------------------------------------
RECORDING_FILE     = "/tmp/aiy_camp_question.wav"
RECORD_FORMAT      = AudioFormat(sample_rate_hz=16000, num_channels=1, bytes_per_sample=2)
MAX_RECORD_SECONDS = 8      # Recording stops here even if the button is still held
REBOOT_HOLD_SECONDS = 10    # Must stay longer than MAX_RECORD_SECONDS

# --- Voice settings ------------------------------------------------------
VOICE_VOLUME = 30
VOICE_PITCH  = 130
VOICE_SPEED  = 100

# --- Musical note frequencies (matches Jupyter notebook) -----------------
NOTE_FREQS = {
    "C": 262, "C#": 277, "D": 294, "D#": 311, "E": 330,
    "F": 349, "F#": 370, "G": 392, "G#": 415, "A": 440,
    "A#": 466, "B": 494,
}


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
            # Volume capped at 50 % to protect classroom ears
            value = int(32767.0 * 0.5 * math.sin(
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

    Accepts single notes ('C', 'D#', 'A') and minor chord arpeggios
    ('Am', 'Dm', 'Gm').  Matches the Jupyter notebook API exactly.
    """
    note = note.upper()
    logging.debug("Playing note %s for %.2fs", note, duration)
    try:
        if note.endswith("M"):
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
    """Block until the computer answers (it may still be booting)."""
    announced = False
    while True:
        try:
            _post("/reset", timeout=5)    # Also clears this Pi's chat memory
            logging.info("Connected to %s as '%s'.", SERVER_URL, PI_NAME)
            return
        except (urllib.error.URLError, OSError, ValueError) as e:
            logging.warning("Server not reachable yet: %s", e)
            if not announced:
                say("Waiting for the computer.")
                announced = True
            time.sleep(3)


def _record_question(board):
    """Record from the mic while the button is held (up to MAX_RECORD_SECONDS)."""
    record_file(
        RECORD_FORMAT,
        filename=RECORDING_FILE,
        filetype="wav",
        wait=lambda: board.button.wait_for_release(timeout=MAX_RECORD_SECONDS),
    )


def _ask_server():
    """Send the recording; returns {"heard", "command", "reply"}."""
    with open(RECORDING_FILE, "rb") as f:
        return _post("/ask", f.read(), "audio/wav")


# =========================================================================
#  BOOT SEQUENCE  —  INSTRUCTORS: PASTE STUDENT CODE HERE
#
#  Replace the contents of this function with the student's Module 4 code
#  (section 1 only — the boot animation).  The personality prompt now lives
#  on the computer in computer/prompts/ — put the student's system_prompt
#  text in a file there instead of here.
#
#  Example student code to paste:
#
#      Turn_On_LED("Green")
#      Play_Note("C", 0.5)
#      Turn_On_LED("Red")
#      Play_Note("G", 0.5)
#
# =========================================================================

def boot_sequence():
    """Run the startup animation."""

    # ------------------------------------------------------------------
    # Boot animation: Imperial March (simplified)
    # ------------------------------------------------------------------
    Turn_On_LED("red")
    Play_Note("G", 0.5)
    Play_Note("G", 0.5)
    Play_Note("G", 0.5)

    Turn_On_LED("green")
    Play_Note("D#", 0.35)
    Play_Note("A#", 0.15)

    Turn_On_LED("red")
    Play_Note("G", 0.5)
    Play_Note("D#", 0.35)
    Play_Note("A#", 0.15)
    Play_Note("G", 1.0)

    Turn_On_LED("off")

    say("All systems online. The Force is strong with this one.")
    Turn_On_LED("green")


# =========================================================================
#  SYSTEM COMMANDS
# =========================================================================

def _power_off():
    say("Goodbye!")
    subprocess.call("sudo shutdown now", shell=True)


def _reboot():
    say("See you in a bit!")
    subprocess.call("sudo reboot", shell=True)


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
#  LONG-PRESS REBOOT MONITOR
# =========================================================================

def _start_long_press_monitor():
    """Start a daemon thread that reboots the Pi if the button is held long enough.

    Every press also records a question, so the hold time is longer than
    MAX_RECORD_SECONDS — a normal question never triggers a reboot.
    This allows students to trigger a clean reboot (which pulls new code from
    GitHub via voicekit_boot.sh) without physically yanking the power cable.
    """
    HOLD_SECONDS = REBOOT_HOLD_SECONDS

    def _monitor():
        while True:
            try:
                # Wait for button press (active LOW on Voice Kit V1)
                while GPIO.input(BUTTON_PIN) != 0:
                    time.sleep(0.05)

                start = time.monotonic()
                while GPIO.input(BUTTON_PIN) == 0:
                    if time.monotonic() - start >= HOLD_SECONDS:
                        logging.warning("LONG PRESS DETECTED — REBOOTING")
                        try:
                            tts.say("Rebooting now.", volume=60)
                        except Exception:
                            pass
                        time.sleep(0.5)
                        subprocess.call(["sudo", "reboot"])
                        return
                    time.sleep(0.05)
            except Exception:
                # GPIO.input may fail briefly before Board initialises the pin.
                # Sleep and retry silently.
                time.sleep(1)

    thread = threading.Thread(target=_monitor, daemon=True, name="long-press")
    thread.start()
    logging.info("Long-press reboot monitor started (hold button %ss to reboot).", HOLD_SECONDS)


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

    # --- Boot sequence (LEDs + sounds) -----------------------------------
    try:
        boot_sequence()
    except Exception as e:
        logging.error("Boot sequence error: %s", e)
        say("Boot error. Starting assistant anyway.")

    # --- Connect to the computer -----------------------------------------
    _wait_for_server()

    try:
        with Board() as board:
            # Start long-press reboot monitor (after Board configures the button)
            _start_long_press_monitor()

            say("Ready!")

            while True:
                board.led.state = Led.BEACON_DARK      # Idle — dim breathing
                logging.info("Hold the button and speak...")

                board.button.wait_for_press()
                board.led.state = Led.ON                # Listening — solid
                _record_question(board)

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
                    say(reply)

    except KeyboardInterrupt:
        logging.info("Interrupted by user.")
    finally:
        Turn_On_LED("off")
        GPIO.cleanup()
        logging.info("GPIO cleaned up. Exiting.")


if __name__ == "__main__":
    main()
