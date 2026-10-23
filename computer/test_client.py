#!/usr/bin/env python3
"""
test_client.py  —  Pretend to be a Voice Kit Pi, using this computer's mic and speakers

Lets you test server.py without a Pi or a cable.  It talks to the server the
same way ai_camp_assistant.py does on the Pi.  Works on macOS, Windows and Linux.

    Terminal 1:  python computer/server.py
    Terminal 2:  python computer/test_client.py

TAP Enter to start talking, tap Enter again to stop (or it stops after 8 seconds).
Don't hold Enter down like the Pi's button — the key repeats and stops the
recording straight away.  Ctrl+C to quit.

Options:
    --name voicekit-3    Pretend to be that Pi (uses prompts/voicekit-3.txt if it exists)
    --wav question.wav   Send a recorded WAV file once instead of using the mic
"""

import argparse
import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave

WINDOWS = sys.platform == "win32"
if WINDOWS:
    import msvcrt
    import winsound
else:
    import select
    import termios

SAMPLE_RATE        = 16000
MAX_RECORD_SECONDS = 8
MIN_RECORD_SECONDS = 0.7    # Shorter than this is almost always a stray key press


def post(server, name, path, body=b""):
    req = urllib.request.Request(
        server + path, data=body,
        headers={"Content-Type": "audio/wav", "X-Pi-Name": name},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


# =========================================================================
#  KEYBOARD  (different on Windows and macOS/Linux)
# =========================================================================

def flush_keys():
    """Throw away any Enter presses typed while we weren't waiting for one."""
    if WINDOWS:
        while msvcrt.kbhit():
            msvcrt.getwch()
        return
    try:
        termios.tcflush(sys.stdin, termios.TCIFLUSH)
    except (termios.error, ValueError):
        pass    # stdin isn't a terminal


def wait_for_enter(timeout):
    """Wait up to *timeout* seconds for Enter.  Returns True if it was pressed."""
    if WINDOWS:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if msvcrt.kbhit() and msvcrt.getwch() in ("\r", "\n"):
                return True
            time.sleep(0.02)
        return False
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if ready:
        sys.stdin.readline()
    return bool(ready)


# =========================================================================
#  AUDIO
# =========================================================================

def record():
    """Record from the mic until Enter is pressed (or MAX_RECORD_SECONDS).

    Returns (wav_bytes, seconds_recorded).
    """
    import sounddevice as sd

    chunks = []
    with sd.RawInputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                           callback=lambda data, frames, t, status: chunks.append(bytes(data))):
        print("  ● Recording... press Enter to stop.")
        if not wait_for_enter(MAX_RECORD_SECONDS):
            print("  (stopped after %d seconds)" % MAX_RECORD_SECONDS)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(b"".join(chunks))
    seconds = sum(len(c) for c in chunks) / 2.0 / SAMPLE_RATE
    return buf.getvalue(), seconds


def play_wav(wav_bytes):
    """Play WAV audio sent by the server (the personality's voice)."""
    if WINDOWS:
        winsound.PlaySound(wav_bytes, winsound.SND_MEMORY)
        return
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
    try:
        player = ["afplay"] if sys.platform == "darwin" else ["aplay", "-q"]
        subprocess.call(player + [f.name])
    finally:
        os.remove(f.name)


def say(text):
    """Speak *text* with this computer's own voice (stands in for the Pi's Classic voice)."""
    try:
        if sys.platform == "darwin":
            subprocess.call(["say", text])
        elif WINDOWS:
            # Built-in Windows speech, text passed on stdin so quotes can't break it
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Add-Type -AssemblyName System.Speech; "
                 "(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak([Console]::In.ReadToEnd())"],
                input=text, text=True,
            )
        else:
            subprocess.call(["espeak", text])
    except OSError:
        pass    # No speech available — the text is printed anyway


def handle(result):
    """Do what the Pi would do with the server's answer.  Returns False to quit."""
    heard = result.get("heard")
    if not heard:
        print("  (nothing heard)")
        return True
    print("You: %s" % heard)

    command = result.get("command")
    if command == "exit":
        say("Goodbye!")
        return False
    if command:
        # Don't actually shut down or reboot this computer
        print("  [The Pi would run the '%s' command here]" % command)
        say("On the Pi, I would %s now." % command.replace("_", " "))
        return True

    reply = result.get("reply") or "Something went wrong."
    print("Bot: %s" % reply)
    if result.get("audio"):
        play_wav(base64.b64decode(result["audio"]))
    else:
        say(reply)
    return True


def main():
    parser = argparse.ArgumentParser(description="Test server.py with this computer's mic")
    parser.add_argument("--server", default="http://localhost:8000")
    parser.add_argument("--name", default="test-pi")
    parser.add_argument("--wav", help="send this WAV file once instead of recording")
    args = parser.parse_args()

    try:
        post(args.server, args.name, "/reset")
    except OSError as e:
        sys.exit("Can't reach the server at %s (%s). Is server.py running?" % (args.server, e))
    print("Connected to %s as '%s'." % (args.server, args.name))

    if args.wav:
        with open(args.wav, "rb") as f:
            handle(post(args.server, args.name, "/ask", f.read()))
        return

    try:
        while True:
            flush_keys()    # Ignore presses made while the bot was talking
            input("\nTap Enter, then speak... ")
            flush_keys()    # Ignore key-repeat if Enter was held down
            audio, seconds = record()
            flush_keys()
            if seconds < MIN_RECORD_SECONDS:
                print("  (too short — tap Enter once to start and once to stop; don't hold it)")
                continue
            print("  Thinking...")
            if not handle(post(args.server, args.name, "/ask", audio)):
                break
    except (KeyboardInterrupt, EOFError):
        print()


if __name__ == "__main__":
    main()
