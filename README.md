# Trikal – Voice AI Companion

Trikal is a personal voice companion I'm building: an AI friend you talk to out loud, that remembers past conversations, switches into the right role for the topic, searches the web when it needs current facts, and lets you interrupt it mid-sentence like a real conversation.

This repository holds the Python prototype that runs on a Mac. The iPhone app version is in progress.

## Features

- **Voice in, voice out:** speech recognition for listening and the built-in macOS voice for speaking (free, no paid voice service).
- **Long-term memory:** every conversation is saved to a local SQLite database. At the end of each session, Claude writes short factual notes, and the most recent notes are loaded into the next conversation.
- **Modes and personas:** starts as a friend, then shifts into career counselor, careful money guide, or morning and health coach depending on the topic. Ask it to act as a new role and it creates and saves that persona for next time.
- **Barge-in:** replies are spoken sentence by sentence while a background thread listens. Start talking and it stops and listens to you.
- **Web search:** Claude decides when it needs current information and calls a web search tool (Tavily), then summarizes what it found in a few spoken sentences.
- **Safety built into the prompt:** encourages leaning on real people, takes signs of distress seriously, and never gives confident financial or medical advice.

## How it evolved

Each file is a working step, kept to show how the project grew:

| File | Step | What it added |
| --- | --- | --- |
| `chat.py` | 1 | Text chat with Claude and conversation history |
| `voice.py` | 2 | Talk and listen out loud |
| `companion_v1.py` | 3 | Long-term memory in SQLite and end-of-session notes |
| `companion.py` | 4 | Modes and saved personas |
| `companion_bi.py` | 5 | Barge-in: interrupt it while it's speaking |
| `companion_ws.py` | 6 | Web search tool use (latest version) |

## How it works

```
microphone ──► speech-to-text ──► Claude (system prompt + memory + roles)
                                        │
                                        ├── web_search tool (Tavily) when needed
                                        ▼
speaker ◄── macOS "say" (sentence by sentence, interruptible) ◄── reply
                                        │
                                        ▼
                         SQLite: messages, notes, personas
```

## Setup (macOS)

```bash
brew install portaudio
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Set your API keys as environment variables (never in the code):

```bash
export ANTHROPIC_API_KEY=your-anthropic-key
export TAVILY_API_KEY=your-tavily-key
```

Run the latest version:

```bash
python companion_ws.py
```

Say "goodbye" to end the session. Notes are saved to `memory.db`, which stays local and is excluded from Git.

## Roadmap

- Native iPhone app built in Xcode, with a calm deep-blue and teal design
- A warmer, more natural voice
- A companion for family members that checks in on meals and medicines and sends updates

## Tech

Python · Claude API (tool use) · SpeechRecognition · PyAudio · SQLite · Tavily · threading
