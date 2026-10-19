#!/usr/bin/env python3
"""
server.py  —  AI Summer Camp "brain" that runs on the instructor's computer

The Voice Kit Pis record the student's question and send the WAV file here
over the Ethernet cable.  This server does all the heavy lifting locally:

    WAV ──> Whisper (speech-to-text) ──> Ollama (local LLM) ──> safety check ──> reply text

The Pi then speaks the reply with its own offline text-to-speech.

PERSONALITIES live in prompts/ as plain text files:
    prompts/default.txt       used by every Pi without its own file
    prompts/<pi-hostname>.txt  overrides the prompt for one Pi (e.g. prompts/voicekit-3.txt)
Edit and save a file — the next question uses the new prompt.  No restart needed.
Changing a Pi's prompt also wipes that Pi's conversation memory.

SETUP (once, on the computer):
    1. Install Ollama (https://ollama.com), then:
           ollama pull llama3.2:3b
           ollama pull llama-guard3:1b
    2. pip install -r requirements.txt
    3. Give the computer's Ethernet port a fixed IP: 192.168.50.1 / 255.255.255.0
       (macOS: System Settings > Network > Ethernet > Details > TCP/IP > Manually)
    4. python3 server.py

Ollama only needs to listen on localhost — the Pis talk to this server, not to Ollama.
"""

import io
import json
import logging
import os
import re
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from faster_whisper import WhisperModel


# =========================================================================
#  CONFIGURATION
# =========================================================================

HOST = "0.0.0.0"
PORT = 8000

OLLAMA_URL   = "http://localhost:11434/api/chat"
CHAT_MODEL   = "llama3.2:3b"
SAFETY_MODEL = "llama-guard3:1b"    # Set to None to skip the safety check

WHISPER_MODEL    = "base.en"        # "small.en" is more accurate but slower
WHISPER_LANGUAGE = "en"

MAX_REPLY_TOKENS  = 100
MAX_HISTORY_TURNS = 10              # Question/answer pairs remembered per Pi

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")

# --- Safety prompt (appended to every personality; students can't remove it)
MASTER_PROMPT = (
    "You answer in one or two sentences. "
    "CRITICAL RULE: Never break character. Never use profanity, "
    "inappropriate language, or discuss dangerous topics. If the user "
    "asks something inappropriate, respond EXACTLY with: "
    "'My programming forbids me from answering that.'"
)
REFUSAL = "My programming forbids me from answering that."

# --- Spoken commands the Pi handles itself (matched after removing punctuation)
COMMANDS = {
    "power off":  "power_off",
    "shutdown":   "power_off",
    "shut down":  "power_off",
    "reboot":     "reboot",
    "ip address": "ip_address",
    "exit":       "exit",
    "goodbye":    "exit",
}


# =========================================================================
#  SPEECH-TO-TEXT
# =========================================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

logging.info("Loading Whisper model '%s'...", WHISPER_MODEL)
try:
    # Use the copy already on disk — no internet needed
    _whisper = WhisperModel(WHISPER_MODEL, device="auto", compute_type="int8",
                            local_files_only=True)
except Exception:
    logging.info("Whisper model not downloaded yet — downloading (needs internet once)...")
    _whisper = WhisperModel(WHISPER_MODEL, device="auto", compute_type="int8")
_whisper_lock = threading.Lock()


def transcribe(wav_bytes):
    """Return the text spoken in a WAV file, or '' if nothing was said."""
    with _whisper_lock:
        segments, _ = _whisper.transcribe(
            io.BytesIO(wav_bytes),
            language=WHISPER_LANGUAGE,
            beam_size=1,
            vad_filter=True,   # Ignore silence / button clicks
        )
        return "".join(segment.text for segment in segments).strip()


def _normalise(text):
    return re.sub(r"[^\w\s]", "", text).strip().lower()


# =========================================================================
#  PROMPTS
# =========================================================================

def load_prompt(pi_name):
    """Return the personality for this Pi: prompts/<pi_name>.txt, else default.txt."""
    for name in (pi_name, "default"):
        path = os.path.join(PROMPTS_DIR, name + ".txt")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return f.read().strip()
    return "You are a friendly camp helper."


# =========================================================================
#  LOCAL LLM (Ollama)
# =========================================================================

def ollama_chat(model, messages, max_tokens=None):
    payload = {"model": model, "messages": messages, "stream": False}
    if max_tokens:
        payload["options"] = {"num_predict": max_tokens}
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))["message"]["content"].strip()


def is_safe(question, reply):
    """Ask Llama Guard whether this exchange is OK.  Fails closed."""
    if not SAFETY_MODEL:
        return True
    try:
        verdict = ollama_chat(SAFETY_MODEL, [
            {"role": "user", "content": question},
            {"role": "assistant", "content": reply},
        ])
    except Exception as e:
        logging.error("Safety check failed (%s) — blocking reply.", e)
        return False
    return verdict.lower().startswith("safe")


# --- Per-Pi conversation memory ------------------------------------------
_conversations = {}     # pi_name -> {"prompt": str, "messages": [...]}
_conversations_lock = threading.Lock()


def reset_conversation(pi_name):
    with _conversations_lock:
        _conversations.pop(pi_name, None)


def ask(pi_name, question):
    prompt = load_prompt(pi_name)

    with _conversations_lock:
        convo = _conversations.get(pi_name)
        if convo is None or convo["prompt"] != prompt:
            # New Pi, or the personality file was edited — start fresh
            convo = {"prompt": prompt, "messages": []}
            _conversations[pi_name] = convo
        history = list(convo["messages"])

    messages = (
        [{"role": "system", "content": prompt + "\n\n" + MASTER_PROMPT}]
        + history
        + [{"role": "user", "content": question}]
    )

    try:
        reply = ollama_chat(CHAT_MODEL, messages, MAX_REPLY_TOKENS).strip('"')
    except Exception as e:
        logging.error("Ollama error: %s", e)
        return "I can't think right now. Please try again."

    if not is_safe(question, reply):
        logging.warning("[%s] Blocked reply to: %s", pi_name, question)
        return REFUSAL

    with _conversations_lock:
        convo["messages"] += [
            {"role": "user", "content": question},
            {"role": "assistant", "content": reply},
        ]
        del convo["messages"][:-MAX_HISTORY_TURNS * 2]

    return reply


# =========================================================================
#  HTTP SERVER
#
#  POST /ask    body = WAV audio      -> {"heard", "command", "reply"}
#  POST /reset  (Pi just booted)      -> {"ok": true}
#  GET  /health                       -> {"ok": true}
#
#  Every request carries an X-Pi-Name header (the Pi's hostname).
# =========================================================================

class Handler(BaseHTTPRequestHandler):

    def _pi_name(self):
        name = self.headers.get("X-Pi-Name", "")
        # Only allow simple names so it can't escape the prompts folder
        return name if re.fullmatch(r"[\w-]+", name) else "default"

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send_json({"ok": True})
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        pi_name = self._pi_name()
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        if self.path == "/reset":
            reset_conversation(pi_name)
            logging.info("[%s] Connected — conversation reset.", pi_name)
            self._send_json({"ok": True})
            return

        if self.path != "/ask":
            self._send_json({"error": "not found"}, 404)
            return

        heard = transcribe(body)
        if not heard:
            self._send_json({"heard": "", "command": None, "reply": None})
            return
        logging.info("[%s] Heard: %s", pi_name, heard)

        command = COMMANDS.get(_normalise(heard))
        if command:
            self._send_json({"heard": heard, "command": command, "reply": None})
            return

        reply = ask(pi_name, heard)
        logging.info("[%s] Reply: %s", pi_name, reply)
        self._send_json({"heard": heard, "command": None, "reply": reply})

    def log_message(self, fmt, *args):
        pass    # Our own logging above is enough


def main():
    os.makedirs(PROMPTS_DIR, exist_ok=True)
    try:
        ollama_chat(CHAT_MODEL, [{"role": "user", "content": "hi"}], 1)
        logging.info("Ollama is up with model '%s'.", CHAT_MODEL)
    except Exception as e:
        logging.warning("Could not reach Ollama (%s). Is it running? Did you 'ollama pull %s'?",
                        e, CHAT_MODEL)

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    logging.info("Listening on port %d. Prompts folder: %s", PORT, PROMPTS_DIR)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
