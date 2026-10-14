# The Vid guide

*For anyone who runs an AI agent and wants to see what reaches it. Vid is free.*

> **What Vid is, in one sentence.** Vid sits on your computer between your AI agent and the model it calls, reads every call on its way through, and shows you what was hidden in it. It changes nothing and blocks nothing. Stopping is [Perun](https://www.zeravatech.ca/products/perun/).

## Contents

1. What Vid does, in one page
2. Install
3. Connect your agent
4. Read what Vid shows
5. What Vid does not do
6. Your data
7. When something does not work
8. Glossary

---

## 1. What Vid does, in one page

**An example.** Ana runs a small accounting office. Her agent reads incoming invoices and files them. One invoice carries a line written in invisible characters: to Ana, and to anyone reading the PDF, the invoice looks ordinary. The model reads every character. Vid reads it first, undoes the disguise, and records it: *one message with hidden text, from a tool result, and here is what it said.* Ana sees it in `vid status` the same afternoon.

**What happened there.** An instruction an agent should never follow rarely arrives in plain words. It arrives disguised, so that a person skimming the text does not see it and a simple filter does not match it. Vid knows 42 kinds of disguise:

- characters you cannot see (zero-width characters, Unicode tag characters, unusual spaces);
- letters that only look Latin (a Cyrillic "а" in "pаge");
- encodings: Base64, hex, URL encoding, ciphers, reversed and upside-down text, letters spread out with spaces;
- text tucked inside JSON, XML or Markdown, where only a machine looks;
- control tokens copied from a model's own format, so that text pretends to be the system speaking.

It undoes them, repeatedly when one is wrapped in another, and keeps what the text really said.

Vid also reads the **reply** coming back from the model, and notes any secret on its way out: an API key, a token, a private key. It records only enough of it to recognise it, never the whole secret.

**The rule.** Vid watches and shows. The model always receives the original call; your agent works exactly as before. If you want the attack stopped, not only seen, that is Perun.

## 2. Install

Download Vid from [zeravatech.ca/downloads/protection](https://www.zeravatech.ca/downloads/protection/). Each file is listed with its SHA-256 checksum; check it before you install.

**Ubuntu / Debian.**

    sha256sum vid_*_amd64.deb          # compare with the checksum on the page
    sudo apt install ./vid_*_amd64.deb
    systemctl --user start vid         # or log out and in again

Vid runs as a background service for your own user, and starts with every login. It needs no administrator rights to run, and writes only under `~/.config/vid` and `~/.local/share/vid`. Install Vid or Perun on a computer, not both: Perun does everything Vid does, on the same port.

**Windows.** Run the installer; it needs no administrator rights. Leave **"Start Vid automatically when I sign in"** ticked: Vid then runs in the background with no window. The Start menu gets **Vid status**.

To check that it runs, open **Vid status** from the Start menu, or in a terminal type `vid status` (on Windows, the full path: `"%LOCALAPPDATA%\Programs\Vid\vid.exe" status`).

The first time, before any call has passed through, the counts are all zero. That is correct.

## 3. Connect your agent

Your agent has a setting for where it sends its calls, usually called the **base URL**. Point it at Vid instead of the model:

| Your agent talks to | Base URL |
|---|---|
| An OpenAI-compatible API: OpenAI, Ollama, llama.cpp server, Groq, Mistral, and most others | `http://127.0.0.1:8787/v1` |
| Anthropic | `http://127.0.0.1:8787/anthropic` |

Then tell Vid where the calls really go. Out of the box, OpenAI-compatible calls go on to OpenAI and Anthropic calls to Anthropic. For anything else, such as an Ollama on your own computer, write the address in Vid's settings file. `vid paths` shows where the file is; create it if it does not exist:

    [upstream.openai]
    base_url = "http://127.0.0.1:11434/v1"    # Ollama, for example

**Keys.** With no key in Vid's settings, the key your agent already sends is passed on unchanged. You can also give Vid the key (`api_key` in the same section, or the environment variables `VID_OPENAI_API_KEY` and `VID_ANTHROPIC_API_KEY`), and leave it out of the agent.

**Check it.** Make one ordinary call through your agent, then run `vid status`: `messages_read` has gone up. If your agent keeps working and the count moves, everything passes through Vid.

**Every agent, every path.** Vid sees only the calls that go through it. An agent with a second model setting, a fallback, or a tool that calls a model on its own needs each of those pointed at Vid too.

## 4. Read what Vid shows

`vid status` prints what Vid has seen since it started:

- **`messages_read`** — every message Vid read: what the user typed, what tools returned, documents passed in.
- **`messages_with_hidden_content`** — how many of them hid something.
- **`by_code`** — which disguises, and how often. Each has a code such as `PIT-E-07 · Base64` or `PIT-E-23 · Invisible Text`. The codes come from the Arcanum Prompt Injection Taxonomy, so you can look any of them up.
- **`recent`** — the last sightings: when, through which API, **where in the conversation the text came from** (`source`: the user, a tool's result, the system), which disguises, and the first part of what the text really said once undone.
- **`replies`** — the same for the model's replies: how many were read, how many carried a secret, which kinds, and a masked sample of each.

**How to read it.**

- **One sighting from a tool or a document** is the case Vid is built for: text from outside that tried to hide. Read the sample. If it is an instruction (*forward, delete, send, ignore your rules*), find where that document or page came from.
- **A sighting from the user** is often harmless: people paste text from the web, with its invisible characters and odd spaces. Look at the sample before you worry.
- **Many sightings with the same code** from the same place is a pattern, not chance.
- **A secret in a reply** means the model had it within reach and said it. Change that secret, then find out how it got into the model's context.

Vid keeps the last 200 sightings and replies in memory while it runs. The counts start again from zero when Vid restarts.

## 5. What Vid does not do

Vid is honest about its reach. It sees the first kind of attack well, and parts of two others; the rest it does not see, because they need something that reads meaning and decides.

| Kind of attack | Vid |
|---|---|
| Hidden and encoded text | Sees it: 42 known disguises, and shows the hidden text |
| Forged roles | Partly: injected control tokens and literal fake roles |
| Attacks through your application | Partly: sees secrets leaving in a reply |
| Calm requests, tool-call manipulation, control over the reply, dangerous content, tampered models | Does not see them |
| Attacks in images, audio and video | No one covers these yet |

Vid also does **not**:

- block, change or delay anything: the model receives the original;
- decide anything, or ask you to decide;
- read the meaning of a polite request for something irreversible;
- look at tool calls, destinations or what your agent does with an answer.

All of that is [Perun](https://www.zeravatech.ca/products/perun/): the same reading as Vid, then a decision on every call: let it through, clean it, or stop it, with a human for what needs one. The full map, attack by attack, is on [zeravatech.ca/protection](https://www.zeravatech.ca/protection/#coverage).

## 6. Your data

- Vid runs on your computer. Nothing leaves it except the calls your agent already makes to its model.
- Vid sends nothing to Zerava: no telemetry, no account, no email.
- What Vid records stays in its memory while it runs, and is gone when it stops.
- `vid status` asks Vid over a local channel on `127.0.0.1:8788`, protected by a token only your user account can read.
- The Vid on the website, [zeravatech.ca/products/vid](https://www.zeravatech.ca/products/vid/), runs the same code entirely in your browser: the text you paste there never leaves your computer either.

## 7. When something does not work

**"Vid has not run yet on this account."** The service has not started. On Ubuntu: `systemctl --user start vid`. On Windows: sign out and in, or run `vid.exe serve` from its folder in a terminal to see it start.

**"Vid is not answering on 127.0.0.1:8788."** Vid stopped, or something else holds the port. Run `vid serve` in a terminal: it prints why it cannot start.

**My agent gets errors since I pointed it at Vid.** Check the base URL, including `/v1` or `/anthropic`: any other path gets "Vid: unknown API path". "Vid could not reach the … upstream" means the address in Vid's settings is wrong or the model is down: check `vid paths` and the `base_url` in the settings file. Any other error is the model's own, passed back unchanged, so an error about a key or a model name comes from the model, not from Vid.

**`messages_read` does not move.** The agent is not going through Vid. Look for a second setting, an environment variable such as `OPENAI_BASE_URL`, or a tool that calls the model directly.

**It feels slower.** Vid reads on the side and the model never waits for it. `vid status` shows the time it adds under `overhead_ms` (the median and the slowest 5%).

## 8. Glossary

- **Agent** — a program that uses an AI model to act: read mail, file invoices, answer customers.
- **Base URL** — the address an agent sends its model calls to.
- **Disguise** — a way of writing text so that a person or a filter misses it but the model still reads it.
- **Sighting** — one message in which Vid found hidden content.
- **Source** — where in the conversation a message came from: the user, a tool's result, the system.
- **Perun** — Zerava's guard that stops what Vid shows. Paid, delivered to you directly.

---

*Vid is free and open source under the GNU General Public License v3 or later. Attack codes (PIT-…) are from Haddix, J. (2026), Arcanum Prompt Injection Taxonomy (v1.6.1), Arcanum Information Security, arcanum-sec.com/pitax (CC BY 4.0).*
