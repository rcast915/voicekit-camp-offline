# VoiceKit Camp — Offline Edition

A voice assistant for AI summer camps, built on the **Google AIY Voice Kit V1**, that runs with **no internet connection**.

Students hold the Voice Kit's button and ask a question. The Raspberry Pi sends the recording over an Ethernet cable to the instructor's computer, which turns the speech into text, writes a reply with a local AI model, checks the reply for safety, and sends it back. The Pi then speaks the reply aloud.

Based on [briancasio/voicekit-camp](https://github.com/briancasio/voicekit-camp), which used Google Cloud Speech and the Gemini API. This version swaps both for local models and moves the bot's personality out of the Pi's code and into text files on the computer.

```
[Voice Kit Pi] ── Ethernet ──> [Instructor's computer]
 button, mic, LEDs,              Whisper          speech → text
 speaker, offline TTS            Ollama           llama3.2:3b writes the reply
                                 Llama Guard      blocks unsafe replies
```

## What's in the repo

| Path | Runs on | What it does |
|---|---|---|
| `ai_camp_assistant.py` | Pi | Boot animation, hold-to-talk recording, speaks replies, handles voice commands |
| `voicekit.service` | Pi | systemd unit that starts the assistant at boot |
| `computer/server.py` | Computer | Speech-to-text, the local AI model and the safety check, served over HTTP on port 8000 |
| `computer/editor.html` | Computer | Personality editor page, served at http://localhost:8000 |
| `computer/prompts/` | Computer | Bot personalities: `default.txt`, or `<pi-hostname>.txt` for one Pi |
| `computer/test_client.py` | Computer | Stands in for a Pi using the computer's own mic and speakers, so you can test without one |

## Setting up the computer

You need internet once for this setup. After that, everything runs offline.

1. Install [Ollama](https://ollama.com), then download the two models:
   ```bash
   ollama pull llama3.2:3b
   ollama pull llama-guard3:1b
   ```
2. Create a Python 3.11 environment and install the requirements:
   ```bash
   conda create -n voicekit python=3.11 -y
   conda activate voicekit
   pip install -r computer/requirements.txt
   ```
3. Start the server:
   ```bash
   python computer/server.py
   ```
   The first start downloads the Whisper speech model. Later starts load it from disk.

To test without a Pi, run `python computer/test_client.py` in a second terminal. Tap Enter to start talking and tap it again to stop.

## Setting up each Pi

1. Connect the Pi to the computer with an Ethernet cable.
2. Give the computer the fixed IP `192.168.50.1`, and give each Pi its own address (`192.168.50.2`, `.3`, …) in `/etc/dhcpcd.conf`:
   ```
   interface eth0
   static ip_address=192.168.50.2/24
   ```
3. Copy `ai_camp_assistant.py` to the Pi. If the computer isn't at `192.168.50.1`, change `SERVER_URL` at the top of the file.
4. Install the service (instructions are at the top of `voicekit.service`).

The Pi needs no extra Python packages.

## Changing a personality

With the server running, open **http://localhost:8000** on the computer. Pick a personality, edit it and click Save, or try a test question first. Pis that have connected show up in the list, and you can give any of them its own personality. The editor only opens on the server computer itself, so the Pis and other devices on the network can't change prompts.

You can also edit the files directly: `computer/prompts/default.txt`, or `computer/prompts/<pi-hostname>.txt` for a single Pi. The next question uses the new prompt, with no restart. Changing a Pi's prompt also clears its conversation memory.

The server always adds a safety rule to every prompt, so a student's prompt can't remove it.

## Using it

- **Hold the button** while you talk, up to 8 seconds.
- Say **"reboot"**, **"shutdown"**, **"ip address"** or **"goodbye"** for system commands.
- Holding the button for **10 seconds** reboots the Pi.
- Replies blocked by the safety check are spoken as: *"My programming forbids me from answering that."*
