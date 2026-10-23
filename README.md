# VoiceKit Camp — Offline Edition

A talking AI assistant for orange and blue day, built on the **Google AIY Voice Kit V1**, that runs with **no internet connection**.

Students hold the Voice Kit's button and ask a question. The Raspberry Pi inside the kit sends the recording over an Ethernet cable to the instructor's computer. The computer turns the speech into text, writes a reply in the bot's personality with a local AI model, checks the reply for safety, and sends it back. The Voice Kit then speaks the reply out loud.

```
 [Voice Kit / Raspberry Pi] ─── Ethernet cable ───> [Instructor's computer]
  button, mic, speaker, LEDs                         Whisper       speech → text
  startup tune + LEDs                                llama3.2:3b   writes the reply
  plays the reply                                    Llama Guard   blocks unsafe replies
                                                     Web editor    personalities + voices
```

Nothing goes to the internet, and there are no API keys, accounts or usage costs.

Based on [briancasio/voicekit-camp](https://github.com/briancasio/voicekit-camp), which used Google Cloud Speech and the Gemini API. This version replaces both with local models, and moves the bot's personality into a web editor on the computer.

**Contents:** [What you need](#what-you-need) · [Part 1: Set up the computer](#part-1-set-up-the-computer-once) · [Part 2: Set up each Voice Kit](#part-2-set-up-each-voice-kit-once-per-kit) · [Part 3: Every day at camp](#part-3-every-day-at-camp) · [Using the Voice Kit](#using-the-voice-kit) · [The personality editor](#the-personality-editor) · [Students' code](#students-code-boot_sequencepy) · [Troubleshooting](#troubleshooting)

---

## What you need

| | |
|---|---|
| **Voice Kit** | Google AIY Voice Kit V1 on a Raspberry Pi 3, running Raspberry Pi OS with the AIY Python library installed. The camp kits already have this. |
| **Computer** | A **Mac** or **Windows** PC that can run a small AI model: ideally 16 GB of memory, 8 GB at minimum. An Apple Silicon Mac works best. |
| **Cable** | An Ethernet cable, plus a USB-C (or USB) to Ethernet adapter if your computer has no Ethernet port. To connect several kits at once, use a small network switch. |
| **The kit's password** | Ask whoever set up the kits for the password of the `pi` user. |
| **Internet, once** | Only for downloading everything in Part 1. After that, it all runs offline. |

**Mac or Windows?** Everything works on both. The only difference is the **character voices** (robot, wizard, pirate…), which use voices built into macOS. On Windows, every kit speaks with **Classic**, the Voice Kit's own built-in voice.

**Where to type commands:**
- **Mac:** the **Terminal** app.
- **Windows:** **Anaconda Prompt** for anything with `conda` or `python`; **PowerShell** for everything else.
- **On the Voice Kit:** after you log in with `ssh` (Part 2), the same window runs commands on the kit instead. Type `exit` to get back to your computer.

---

## Part 1: Set up the computer (once)

### 1.1 Get the code

```bash
git clone https://github.com/rcast915/voicekit-camp-offline.git
cd voicekit-camp-offline
```
No git? On the GitHub page, click **Code → Download ZIP**, unzip it, and `cd` into the folder. **Run every command in this guide from this folder.**

### 1.2 Install Ollama and the AI models

1. Download and install Ollama from **https://ollama.com** (Mac and Windows installers).
2. Download the two models (about 3 GB):
   ```bash
   ollama pull llama3.2:3b
   ollama pull llama-guard3:1b
   ```
   On an older or slower computer, use the smaller `llama3.2:1b` instead, and set `CHAT_MODEL = "llama3.2:1b"` at the top of `computer/server.py`.

### 1.3 Install Python and the server's packages

1. Install **Miniconda** from **https://docs.anaconda.com/miniconda/** if you don't already have conda.
2. Create an environment with Python 3.11, since some packages don't support the newest Python yet:
   ```bash
   conda create -n voicekit python=3.11 -y
   conda activate voicekit
   pip install -r computer/requirements.txt
   ```

### 1.4 Give the computer's Ethernet port a fixed address

The kits look for the computer at **`192.168.50.1`**. Plug the Ethernet adapter in first so it shows up in the settings.

**Mac:**
1. **System Settings → Network**, then click your Ethernet adapter. If it isn't listed, check **Other Services**.
2. **Details… → TCP/IP**.
3. Configure IPv4: **Manually** · IP Address: **`192.168.50.1`** · Subnet Mask: **`255.255.255.0`** · Router: *leave blank* → **OK**.

**Windows:**
1. **Settings → Network & internet → Ethernet**. Pick the adapter if you have more than one.
2. Next to **IP assignment**, click **Edit** → **Manual** → turn on **IPv4**.
3. IP address: **`192.168.50.1`** · Subnet mask: **`255.255.255.0`** (Windows 10 may ask for a *subnet prefix length*: enter **`24`**) · Gateway: *leave blank* → **Save**.

Wi-Fi keeps working as normal; this only affects the cable to the Voice Kits.

### 1.5 Windows only: let the kits through the firewall

Windows blocks incoming connections on a direct cable by default. Open **PowerShell as administrator** (right-click Start → *Terminal (Admin)*) and run:
```powershell
New-NetFirewallRule -DisplayName "VoiceKit server" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
```
If Windows later asks whether to allow Python on networks, click **Allow**.

### 1.6 Start the server and test it

```bash
conda activate voicekit
python computer/server.py
```
The first start downloads the Whisper speech model (about 150 MB). It's ready when it prints `Listening on port 8000`. Leave this window open.

**Check it works before touching a kit.** In a **second** window, run:
```bash
conda activate voicekit
python computer/test_client.py
```
This pretends to be a Voice Kit, using your computer's mic and speakers. **Tap** Enter, ask a question, then **tap** Enter again. Don't hold it down. You should hear an answer. Press Ctrl+C to quit.

Also open **http://localhost:8000** in a browser to see the personality editor.

---

## Part 2: Set up each Voice Kit (once per kit)

This takes about 15 minutes per kit. **Keep the server from 1.6 running**, since the last step tests the connection.

### 2.1 Connect the kit

Plug the kit into your computer with the Ethernet cable, then plug in the kit's power. Wait about **1 minute** for it to start. It may play a tune from its old setup; that's fine.

### 2.2 Find the kit's real name

Each kit has a network name like `voicekit-2`. **Don't trust the label on the box:** a kit labeled 5 may really be `voicekit-2`.

**Mac:**
```bash
dns-sd -B _workstation._tcp local.
```
Wait a few seconds. You should see a line like `voicekit-2 [b8:27:eb:90:82:97]`. That first part is the name. Press Ctrl+C to stop.

**Windows (PowerShell):**
```powershell
1..10 | ForEach-Object { $n = "voicekit-$_.local"; if (Test-Connection $n -Count 1 -Quiet -ErrorAction SilentlyContinue) { "Found $n" } }
```

Nothing found? Wait a minute and try again; see the note in 2.3 about dropouts. If it still isn't found, connect a screen and keyboard to the kit, log in, and type `hostname`.

In the rest of this guide, **replace `voicekit-2` with your kit's name**, and **`102` with 100 plus the number in its name** (`voicekit-4` → `104`).

### 2.3 Copy your SSH key to the kit and fix its permissions

An SSH key lets you log into the kit without typing its password every time.

1. **Make a key, once per computer.** Skip this if you already have one (a file in `~/.ssh/` ending in `.pub`):
   ```bash
   ssh-keygen -t ed25519
   ```
   Press Enter to accept each question. A passphrase is optional.
2. **Copy the key to the kit.** This also fixes a permissions problem on the camp kits that otherwise makes SSH ignore the key. Answer `yes` if asked about the fingerprint, then type the kit's password.

   **Mac:**
   ```bash
   cat ~/.ssh/id_ed25519.pub | ssh pi@voicekit-2.local "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 755 ~ && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
   ```
   **Windows (PowerShell):**
   ```powershell
   type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh pi@voicekit-2.local "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 755 ~ && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
   ```
   If your key is named `id_rsa.pub` instead, use that file name.
3. **Check it:** `ssh pi@voicekit-2.local hostname` should print the kit's name **without asking for the password**. If your key has a passphrase it asks for that instead, which is fine. On a Mac, `ssh-add --apple-use-keychain ~/.ssh/id_ed25519` remembers it.

> **"Operation timed out" or "Could not resolve hostname" every few minutes?** That's expected until step 2.4. The kit keeps looking for a router that isn't there, gives up, and **drops off the cable for about 5 minutes**, then comes back. This command waits until the kit is back, then logs in:
>
> **Mac:** `until nc -z -G 2 voicekit-2.local 22; do sleep 2; done; ssh pi@voicekit-2.local`
>
> **Windows:** `while (-not (Test-NetConnection voicekit-2.local -Port 22 -InformationLevel Quiet -WarningAction SilentlyContinue)) { Start-Sleep 2 }; ssh pi@voicekit-2.local`

### 2.4 Give the kit a fixed address

This stops the dropouts for good. Log into the kit:
```bash
ssh pi@voicekit-2.local
```
**Now on the kit**, check the name of its wired connection:
```bash
nmcli -t -f NAME,DEVICE con show
```
Look for the line ending in `:eth0`. It's usually `Wired connection 1`. Then run these two commands, using **your** number instead of `102`:
```bash
sudo nmcli con mod "Wired connection 1" ipv4.method manual ipv4.addresses 192.168.50.102/24 ipv4.gateway "" ipv6.method link-local
sudo systemd-run --on-active=3 nmcli con up "Wired connection 1"
```
The second command switches the network over after 3 seconds, so type `exit` right away. Then reconnect from your computer using the new address, and answer `yes` to the fingerprint question:
```bash
ssh pi@192.168.50.102 hostname
```
From now on, use **`pi@192.168.50.102`** for this kit.

### 2.5 Copy the program onto the kit

**On your computer**, in the repo folder:
```bash
scp ai_camp_assistant.py boot_sequence.py voicekit.service pi@192.168.50.102:
```

### 2.6 Make it start automatically

Log in with `ssh pi@192.168.50.102`, then **on the kit** run:
```bash
mkdir -p ~/voicekit-offline
mv ~/ai_camp_assistant.py ~/boot_sequence.py ~/voicekit-offline/
[ -f /etc/systemd/system/voicekit.service ] && cp /etc/systemd/system/voicekit.service ~/voicekit.service.backup
sudo cp ~/voicekit.service /etc/systemd/system/voicekit.service
sudo systemctl daemon-reload
sudo systemctl enable --now voicekit.service
```
The third line saves a copy of the kit's old startup service, in case you ever want to switch back.

### 2.7 Test it

Still on the kit:
```bash
curl http://192.168.50.1:8000/health
```
It should print **`{"ok": true}`**. If it doesn't, see [Troubleshooting](#troubleshooting).

The kit should now play the **Futurama** startup tune and say **"Ready!"** **Hold the button, ask a question, and let go.** It should answer within a few seconds. Type `exit` to leave the kit.

### 2.8 Relabel the kit

Put a sticker on the kit with its real name and address, e.g. **`voicekit-2 · 192.168.50.102`**.

**Several kits at once:** connect them all to a network switch, and plug the switch into your computer. Each kit's address uses its own number, so they don't clash.

---

## Part 3: Every day at camp

1. **Start the computer side.** Make sure **Ollama** is running (it usually starts at login; otherwise open the Ollama app), then:

   **Mac:**
   ```bash
   conda activate voicekit
   caffeinate -i python computer/server.py
   ```
   `caffeinate` keeps the Mac awake while the server runs.

   **Windows (Anaconda Prompt):**
   ```bash
   conda activate voicekit
   python computer/server.py
   ```
   And make sure Windows won't sleep: **Settings → System → Power → Screen and sleep → When plugged in, put my device to sleep after: Never**.

   If the computer sleeps, every kit stops answering. Keep it plugged in with the lid open.
2. **Turn on the kits.** Plug in their cables and power. Each one plays its tune and says **"Ready!"** If the computer isn't ready yet, a kit says *"Waiting for the computer"* and keeps trying, so you can start them in any order.
3. **To change personalities,** open **http://localhost:8000** on the computer.

**At the end of the day:** say **"shutdown"** to each kit, or just unplug them. Then press Ctrl+C in the server window.

---

## Using the Voice Kit

| Do this | What happens |
|---|---|
| **Hold the button, talk, then let go** | Asks a question, up to 15 seconds. The light is solid while listening, pulses fast while thinking, and breathes slowly when ready. |
| **Click the button 3 times quickly** | Reboots the kit (about a minute). |
| Say **"reboot"** | Restarts just the assistant, which is quicker. |
| Say **"shutdown"** | Turns the kit off safely. |
| Say **"ip address"** | Speaks the kit's network address. |
| Say **"goodbye"** | Stops the assistant until the next reboot. |

If a question is inappropriate, or the reply fails the safety check, the kit answers: *"My programming forbids me from answering that."*

---

## The personality editor

Open **http://localhost:8000** on the computer running the server. It only opens on that computer; the kits and other devices on the network can't change anything.

- **Default** is the personality for every kit that doesn't have its own. Out of the box it's the 🤖 **Robot**.
- **Voice Kits** lists every kit that has connected. Click **Give it its own** to give that kit a different personality.
- **Starters:** one click on Wizard, Pirate, Robot, Dinosaur, Astronaut, Jedi or Sith fills in a full *Role / Action / Context / Expectation* prompt and a matching voice. Edit the text however you like.

  | Starter | Voice (Mac) | Starter | Voice (Mac) |
  |---|---|---|---|
  | 🧙 Wizard | Grandpa (UK) | 🚀 Astronaut | Reed (US) |
  | 🏴‍☠️ Pirate | Rocko (UK) | 🟢 Jedi | Albert |
  | 🤖 Robot | Zarvox | 🔴 Sith | Ralph |
  | 🦖 Dinosaur | Junior | | |

  Click **▶ Preview** to hear the voice. On Windows, or for personalities that never used a starter, the kit speaks with **Classic**, its own built-in voice.
- **Save** (or Ctrl/⌘+S): the kit's next question uses the new personality and voice. No restart needed.
- **Try it:** ask a test question and read or 🔊 hear the answer, without a kit.
- **Safety:** a safety rule is added to every personality on the server, and every reply is checked by Llama Guard. A student's prompt can't turn either off.

Personalities are saved as files in `computer/prompts/`: `default.txt` and `default.voice.json`, plus `<kit-name>.txt` / `.voice.json` for kits with their own. Only the Default is stored in this repo.

---

## Students' code: `boot_sequence.py`

Each kit's **startup tune, LED show and (optionally) personality** come from `boot_sequence.py`, using the same helpers as the camp notebooks. Paste the student's Module 4 code into it:

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

- **Section 1** plays every time the kit starts. The version in this repo plays a simplified Futurama theme.
- **Section 2** is optional. If the student writes a personality there, the kit sends it to the computer when it starts, and it becomes that kit's personality in the editor. Every restart uses the student's version again. Leave it empty (`""`) to keep the personality set in the editor.

To put a new version on a kit, run this on your computer:
```bash
scp boot_sequence.py pi@192.168.50.102:voicekit-offline/
ssh pi@192.168.50.102 "sudo systemctl restart voicekit"
```

---

## Troubleshooting

| Problem | What to do |
|---|---|
| **Can't find the kit's name** (2.2) | Wait a minute and try again, since it may be in a dropout (see 2.3). Check that the kit has power and that the lights on its Ethernet port are on. If needed, connect a screen and keyboard and type `hostname`. |
| **SSH times out or "could not resolve hostname" every few minutes** | The kit doesn't have its fixed address yet. Use the waiting command in 2.3, then do 2.4. |
| **"Permission denied (publickey,password)"** | Wrong password; ask whoever set up the kits. If it **still** asks for the password after 2.3, redo 2.3. The permission fix in that command is what makes the key work. |
| **"WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED"** | A different kit used that name or address before. Run `ssh-keygen -R 192.168.50.102` (or `-R voicekit-2.local`) and connect again. |
| `curl` in 2.7 fails, or the kit says **"Waiting for the computer"** / **"I can't reach the computer"** | Check that the server is running and the computer isn't asleep. Check that the computer's adapter is set to `192.168.50.1` (1.4). On **Windows**, check the firewall rule (1.5). Check the cable. |
| Kit says **"I can't think right now"** | Ollama isn't running, or the model isn't downloaded. Open the Ollama app, or run `ollama pull llama3.2:3b`. |
| **Every** answer is "My programming forbids me…" | The safety model is missing. Run `ollama pull llama-guard3:1b`. |
| Kit still plays its **old tune** or old code | It's still using its old startup service. Redo 2.6. |
| Answers are slow, or the computer struggles | Use the smaller model (see 1.2), and close other big apps. |
| Questions come out wrong or cut off | Hold the button for the **whole** question and let go after you stop talking. Presses under half a second are ignored. |
| Editor says **"voices need the latest server.py"** | Restart the server (Ctrl+C, then run it again) and refresh the page. |
| Want to watch what a kit is doing | `ssh pi@192.168.50.102 "journalctl -u voicekit -f"`, then Ctrl+C to stop. |
| Switch a kit back to its old setup | `ssh pi@192.168.50.102 "sudo cp ~/voicekit.service.backup /etc/systemd/system/voicekit.service && sudo systemctl daemon-reload && sudo systemctl restart voicekit"` |

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
| `computer/test_client.py` | Computer | Pretends to be a Voice Kit using the computer's mic and speakers (Mac, Windows, Linux) |
| `computer/requirements.txt` | Computer | Python packages for the computer |

The Voice Kit needs no extra Python packages beyond the AIY library.

## Settings worth knowing

At the top of `computer/server.py`:

- `CHAT_MODEL`: the AI model (`llama3.2:3b`). Any Ollama model works; bigger is smarter but slower.
- `SAFETY_MODEL`: `llama-guard3:1b`. Set to `None` to turn the extra safety check off (not recommended with kids).
- `WHISPER_MODEL`: `base.en`. `small.en` understands speech better but is slower.
- `MAX_HISTORY_TURNS`: how many back-and-forth exchanges each kit remembers.

At the top of `ai_camp_assistant.py`: `SERVER_URL` (change it if the computer isn't at `192.168.50.1`), `MAX_RECORD_SECONDS`, and the Classic voice's volume, pitch and speed.

The starter personalities and their voices are in the `TEMPLATES` list in `computer/editor.html`. On a Mac, `say -v '?'` lists every voice you can use.
