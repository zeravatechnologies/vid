# Vid

A local watcher that runs on your computer between an AI agent and the model
it calls. Calls pass through Vid; it reads what reaches the agent and shows
you what is hidden. It does not change the traffic and it does not block:
the model receives the original. Nothing leaves the machine except the calls
the agent already makes.

Vid is the free edition. **Perun**, the paid edition, is the guard that
stops: it reads the meaning of a message and decides, allowing, modifying or
denying each action. Vid shows; Perun acts.

**Status: 0.1.0, observe.** Vid reads every incoming message and undoes
42 kinds of disguise (invisible characters, look-alike letters, Base64 and
other encodings, text inside JSON/XML/Markdown, control tokens), then shows
what was hidden in `vid status`.

## Use

Point the agent's base URL at Vid instead of the model:

| API | Base URL |
|---|---|
| OpenAI-compatible (OpenAI, llama.cpp server, Ollama, Groq, Mistral…) | `http://127.0.0.1:8787/v1` |
| Anthropic | `http://127.0.0.1:8787/anthropic` |

Where the calls go, and the real API keys, are set in Vid's configuration
(`vid paths` shows the file; `src/vid/defaults.toml` lists every key).
With no key in Vid, the agent's own key is passed on.

    vid serve     # the background service runs this
    vid status    # what is protected, what is not, traffic and latency
    vid paths

## Develop

    python3 -m venv .dev/venv
    .dev/venv/bin/pip install -e ".[test]" pyinstaller
    .dev/venv/bin/python -m pytest
    packaging/deb/build.sh .dev/venv/bin/python     # dist/vid_<version>_<arch>.deb

## Documents

- [docs/GUIDE.md](docs/GUIDE.md): the Vid guide (also on
  [zeravatech.ca/docs/vid/guide](https://www.zeravatech.ca/docs/vid/guide/)).
- [web/](web/): the same Vid, running in the browser
  ([zeravatech.ca/products/vid](https://www.zeravatech.ca/products/vid/)).

## Licence

Free and open source under the GNU General Public License v3 or later
(see [LICENSE](LICENSE) and [NOTICE](NOTICE)).

Attack codes (PIT-…) are from Haddix, J. (2026). Arcanum Prompt Injection
Taxonomy (v1.6.1). Arcanum Information Security.
https://www.arcanum-sec.com/pitax (CC BY 4.0).

## Author

Created by **Andrej Ristić**, [Zerava Technologies Inc.](https://www.zeravatech.ca), Toronto.

Source: <https://github.com/zeravatechnologies/vid>
