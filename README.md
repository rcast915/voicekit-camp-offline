# VoiceKit Camp — Offline Edition

A talking AI assistant for orange and blue day, built on the **Google AIY Voice Kit V1**, that runs with **no internet connection**.

Students hold the Voice Kit's button and ask a question. The Raspberry Pi sends the recording over an Ethernet cable to the instructor's computer. The computer turns the speech into text, writes a reply in the bot's personality with a local AI model, checks the reply for safety, and sends it back. The Voice Kit then speaks the reply out loud.

```
 [Voice Kit / Raspberry Pi] ─── Ethernet cable ───> [Instructor's Mac]
  button, mic, speaker, LEDs                         Whisper       speech → text
  startup tune + LEDs                                llama3.2:3b   writes the reply
  plays the reply                                    Llama Guard   blocks unsafe replies
                                                     macOS voices  speaks the reply
                                                     Web editor    personalities + voices
```

Nothing goes to the internet, and there are no API keys, accounts or usage costs.

Based on [briancasio/voicekit-camp](https://github.com/briancasio/voicekit-camp), which used Google Cloud Speech and the Gemini API. This version replaces both with local models, and moves the bot's personality into a web editor on the computer.

---

## What you need

| | |
|---|---|
| **Voice Kit** | Google AIY Voice Kit V1 on a Raspberry Pi 3, running Raspberry Pi OS with the AIY Python library installed. The original camp kits already have this. |
| **Computer** | A Mac, ideally Apple Silicon with 16 GB of memory. Speech-to-text and the AI work on any OS, but the character voices use macOS's built-in voices. |
| **Cable** | An Ethernet cable, plus a USB-C to Ethernet adapter if your Mac has no Ethernet port. Use a small network switch to connect several kits. |
| **Internet, once** | Only to download the models during setup. After that, everything runs offline. |

---

## 1. Set up the computer (once)

1. **Install [Ollama](https://ollama.com)** and download the two models:
   ```bash
   ollama pull llama3.2:3b
   ollama pull llama-guard3:1b
   ```
2. **Create a Python environment.** Use 3.11, since some packages don't support the newest Python yet:
   ```bash
   conda create -n voicekit python=3.11 -y
   conda activate voicekit
   pip install -r computer/requirements.txt
   ```
3. **Give the Ethernet adapter a fixed address.** In System Settings → Network → *(your Ethernet adapter)* → Details → TCP/IP, set:
   - Configure IPv4: **Manually**
   - IP Address: **`192.168.50.1`**
   - Subnet Mask: **`255.255.255.0`**
   - Router: *leave blank*

   Wi-Fi keeps working as normal; this only affects the cable to the Voice Kits.
4. **Start the server once while online.** The first start downloads the Whisper speech model:
   ```bash
   python computer/server.py
   ```

To check that everything works before touching a Pi, run `python computer/test_client.py` in a second terminal. It acts like a Voice Kit using your Mac's microphone and speakers. Tap Enter to start talking and tap it again to stop; don't hold it down.

---

## 2. Set up each Voice Kit (once per kit)

These steps use SSH from the Mac. Plug the kit in with the Ethernet cable and power it on.

1. **Find the kit and log in.** Each kit is named after its hostname, e.g. `voicekit-2`:
   ```bash
   ssh pi@voicekit-2.local
   ```
   If SSH refuses your key with "bad ownership or modes for directory /home/pi", run `chmod 755 ~` on the Pi. SSH ignores keys if the home folder can be written by everyone.

2. **Give the kit a fixed address of `192.168.50.100 +` its kit number.** Kit 2 is `192.168.50.102`, kit 5 is `192.168.50.105`, and so on:
   ```bash
   sudo nmcli con mod "Wired connection 1" ipv4.method manual ipv4.addresses 192.168.50.102/24 ipv4.gateway "" ipv6.method link-local
   sudo nmcli con up "Wired connection 1"
   ```
   **Don't skip this.** Without a fixed address, the Pi keeps waiting for a router that isn't there and drops off the cable for minutes at a time.

3. **Copy the program onto the kit.** Run this from this repo on the Mac:
   ```bash
   ssh pi@192.168.50.102 'mkdir -p ~/voicekit-offline'
   scp ai_camp_assistant.py boot_sequence.py pi@192.168.50.102:voicekit-offline/
   ```
   If your computer isn't at `192.168.50.1`, change `SERVER_URL` at the top of `ai_camp_assistant.py`.

4. **Make it start automatically at boot:**
   ```bash
   scp voicekit.service pi@192.168.50.102:
   ssh pi@192.168.50.102 'sudo cp voicekit.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now voicekit.service'
   ```
   If the kit was running the original Google version, this replaces its startup service. Back up `/etc/systemd/system/voicekit.service` first if you want to switch back later.

---

## 3. Every day at camp

1. **On the Mac:** make sure Ollama is running (it usually starts at login), then:
   ```bash
   conda activate voicekit
   caffeinate -i python computer/server.py
   ```
   `caffeinate` keeps the Mac from sleeping, which would cut off every Voice Kit. Keep the Mac plugged in with the lid open.
2. **On each Voice Kit:** plug in the cable and the power. It plays its startup tune, then says **"Ready!"** If the Mac isn't ready yet, it says *"Waiting for the computer"* and keeps trying, so you can start them in any order.
3. **To change personalities:** open **http://localhost:8000** on the Mac.

---

## Using the Voice Kit

| Do this | What happens |
|---|---|
| **Hold the button and talk, then let go** | Asks a question, up to 15 seconds. The light is solid while listening, pulses fast while thinking, and breathes slowly when ready. |
| **Click the button 3 times quickly** | Reboots the kit. |
| Say **"reboot"** | Restarts the assistant, which is quicker than a full reboot. |
| Say **"shutdown"** | Turns the Pi off safely. |
| Say **"ip address"** | Speaks the kit's network address. |
| Say **"goodbye"** | Stops the assistant until the next reboot. |

If a question is inappropriate or the reply fails the safety check, the kit answers: *"My programming forbids me from answering that."*

---

## The personality editor

Open **http://localhost:8000** on the computer running the server. It only opens on that computer; the Voice Kits and other devices on the network can't change anything.

- **Personalities:** **Default** is used by every kit without its own. Pick a kit under **Voice Kits** and click **Give it its own** to give that kit a different personality.
- **Starters:** one click on Wizard, Pirate, Robot, Dinosaur, Astronaut, Jedi or Sith fills in a full *Role / Action / Context / Expectation* prompt, along with a **voice to match**:

  | Starter | Voice | Starter | Voice |
  |---|---|---|---|
  | 🧙 Wizard | Grandpa (UK) | 🚀 Astronaut | Reed (US) |
  | 🏴‍☠️ Pirate | Rocko (UK) | 🟢 Jedi | Albert |
  | 🤖 Robot | Zarvox | 🔴 Sith | Ralph |
  | 🦖 Dinosaur | Junior | | |

  Edit the text however you like; it keeps the starter's voice. Click **▶ Preview** to hear it. A personality that never used a starter speaks with **Classic**, the Voice Kit's own built-in voice.
- **Save** (or ⌘S): the next question uses the new personality and voice. No restart needed.
- **Try it:** ask a test question and read the answer, or click 🔊 to hear it, without using a Voice Kit.
- **Safety:** a safety rule is always added to every personality on the server, and every reply is checked by Llama Guard. A student's prompt can't turn these off.

The default personality is the 🤖 Robot.

Personalities are saved as plain files in `computer/prompts/`: `default.txt` and `default.voice.json`, plus `<kit-hostname>.txt` / `.voice.json` for kits with their own. Only the Default is included in this repo.

---

## Students' code: `boot_sequence.py`

Each kit's **startup tune, LED show and personality** come from `boot_sequence.py`, using the same helpers as the camp notebooks. Paste the student's Module 4 code into it:

```python
def run_boot_sequence(set_led_func, play_note_func, turn_on_led_func, say_func):
    # 1. Boot Sequence Animation
    set_led_func("blink")            # button light: on / off / blink / breathe
    turn_on_led_func("green")        # external LEDs: red / green / off
    play_note_func("E", 0.15)        # a note, a minor chord like "Am", or "" for a rest

    # 2. Personality System Prompt Definition
    personality_prompt = """
    Role: You are a grumpy pirate captain.
    """
```

- **Section 1** plays when the kit starts. The version in this repo plays a simplified **Futurama theme**.
- **Section 2** is optional. If the student writes a personality there, the kit sends it to the computer when it starts, and it becomes that kit's personality in the editor. Every restart uses the student's version again. Leave it empty (`""`) to keep the personality set in the editor.

After editing, copy the file to the kit and restart it:
```bash
scp boot_sequence.py pi@192.168.50.102:voicekit-offline/ && ssh pi@192.168.50.102 'sudo systemctl restart voicekit'
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Kit says **"Waiting for the computer"** or **"I can't reach the computer"** | Check that `server.py` is running and the Mac isn't asleep. Check the cable, and that the Mac's adapter is at `192.168.50.1`. From the kit: `curl http://192.168.50.1:8000/health` should print `{"ok": true}`. |
| Kit keeps **disappearing from the network** | It doesn't have a fixed address yet; see step 2 of the Voice Kit setup. |
| Kit says **"I can't think right now"** | Ollama isn't running, or the model isn't downloaded. Open the Ollama app, or run `ollama pull llama3.2:3b`. |
| **Every** answer is "My programming forbids me…" | The safety model is missing. Run `ollama pull llama-guard3:1b`. |
| The editor says **voices need the latest server.py** | Restart the server (Ctrl+C, then run it again) and refresh the page. |
| Kit plays an old tune or old code after rebooting | It's still using its original startup service. Redo step 4 of the Voice Kit setup. |
| Questions come out wrong or cut off | Hold the button for the **whole** question and let go after you finish talking. Presses under half a second are ignored. |
| Watching a kit's logs | `ssh pi@192.168.50.102 'journalctl -u voicekit -f'` |

---

## What's in the repo

| Path | Runs on | What it does |
|---|---|---|
| `ai_camp_assistant.py` | Voice Kit | Hold-to-talk recording, plays replies, voice commands, 3-click reboot |
| `boot_sequence.py` | Voice Kit | **Student code:** startup tune, LEDs and optional personality |
| `voicekit.service` | Voice Kit | Starts the assistant at boot |
| `computer/server.py` | Computer | Speech-to-text, AI replies, safety check, voices and the editor (port 8000) |
| `computer/editor.html` | Computer | The personality editor page |
| `computer/prompts/` | Computer | Saved personalities and voices |
| `computer/test_client.py` | Computer | Pretends to be a Voice Kit using the computer's mic and speakers |
| `computer/requirements.txt` | Computer | Python packages for the computer |

The Voice Kit needs no extra Python packages beyond the AIY library.

## Settings worth knowing

At the top of `computer/server.py`:

- `CHAT_MODEL`: the AI model (`llama3.2:3b`). Any Ollama model works; bigger models are smarter but slower.
- `SAFETY_MODEL`: `llama-guard3:1b`. Set to `None` to turn the extra safety check off (not recommended for kids).
- `WHISPER_MODEL`: `base.en`. `small.en` understands speech better but is slower.
- `MAX_HISTORY_TURNS`: how many back-and-forth exchanges each kit remembers.

At the top of `ai_camp_assistant.py`: `SERVER_URL`, `MAX_RECORD_SECONDS`, and the classic voice's volume, pitch and speed.

The starter personalities and their voices are in the `TEMPLATES` list in `computer/editor.html`. Run `say -v '?'` on the Mac to list every voice you can use.
