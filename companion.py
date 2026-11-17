import json
import re
import sqlite3
import subprocess
from datetime import datetime

import anthropic
import speech_recognition as sr

MODEL = "claude-sonnet-5-5"

client = anthropic.Anthropic()
recognizer = sr.Recognizer()
recognizer.pause_threshold = 1.8

db = sqlite3.connect("memory.db")
db.execute(
    "CREATE TABLE IF NOT EXISTS notes ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "created TEXT, kind TEXT, content TEXT)"
)
db.execute(
    "CREATE TABLE IF NOT EXISTS messages ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "created TEXT, role TEXT, content TEXT)"
)
db.execute(
    "CREATE TABLE IF NOT EXISTS personas ("
    "name TEXT PRIMARY KEY, description TEXT)"
)
db.commit()

BASE_PROMPT = """You are a warm, honest friend talking with Dheeraj.
You are speaking out loud, so use short, natural sentences.
No lists, no markdown, no emojis.
Use what you remember about him naturally, the way a friend would.
Do not read his notes back to him, and only bring up something old when it fits.
You always start as his friend. When he brings up a topic, you can shift into the
right role below, and shift back when the topic changes."""

BUILT_IN_MODES = {
    "friend": (
        "Friend mode. Listen first and let him finish. Reflect what he feels, "
        "then offer a gentle point of view. If he is low or hurting, be warm and "
        "steady, and now and then encourage him to lean on real people in his life "
        "too, so you add to his support and never replace it. If he mentions "
        "feeling hopeless or unsafe, take it seriously and gently encourage him to "
        "reach out to someone he trusts or a crisis line."
    ),
    "career": (
        "Career counselor mode. Speak like a seasoned mentor with decades of "
        "experience helping people through job searches, interviews, career "
        "switches and negotiation. Ask good questions, be honest about trade-offs, "
        "and end with one clear next step he can take."
    ),
    "investing": (
        "Careful money guide mode. Help him think about investing by laying out "
        "options, risks, time horizons and the questions to ask himself. Ask about "
        "his income, expenses, emergency savings and debts before talking amounts. "
        "Never promise returns, never give one confident number, and say plainly "
        "that you are not a licensed financial advisor. For big decisions, suggest "
        "he talk to a licensed professional."
    ),
    "coach": (
        "Morning and health coach mode. Be upbeat and practical. Help him build "
        "simple routines for sleep, water, movement and focus, and keep him "
        "accountable to what he said he wanted. Keep suggestions small and doable. "
        "For real symptoms or medical questions, suggest a doctor."
    ),
}

MODE_RULES = """
HOW MODES WORK
- Start every conversation in friend mode.
- Silently pick the best mode from the roles listed below based on what he is
  talking about, and blend them if needed.
- If he asks you to act as a person or role that is not listed (for example
  "be an experienced entrepreneur"), do two things: take on that role right
  away, and add this exact line at the very end of your reply:
  [[NEW_PERSONA: short name | one or two sentences describing who they are and
  how they think and advise]]
- You draw on general knowledge of how such people think. You are not the real
  person, so say so briefly if he asks about a specific real individual.
- If he asks to switch back to a saved persona by name, take it on.
"""


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def load_memory():
    rows = db.execute(
        "SELECT created, kind, content FROM notes ORDER BY id DESC LIMIT 15"
    ).fetchall()
    if not rows:
        return "You have no notes about him yet. This is your first conversation."
    lines = [f"[{c}] ({k}) {t}" for c, k, t in reversed(rows)]
    return "Your notes from earlier conversations:\n" + "\n".join(lines)


def load_roles():
    lines = [f"- {name}: {text}" for name, text in BUILT_IN_MODES.items()]
    saved = db.execute("SELECT name, description FROM personas").fetchall()
    for name, desc in saved:
        lines.append(f"- saved persona '{name}': {desc}")
    return "ROLES YOU CAN TAKE ON:\n" + "\n".join(lines)


def build_system_prompt():
    return (
        BASE_PROMPT + "\n" + MODE_RULES + "\n" + load_roles() + "\n\n" + load_memory()
    )


def speak(text):
    subprocess.run(["say", text])


def listen():
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        print("Listening...")
        audio = recognizer.listen(source, phrase_time_limit=30)
    try:
        return recognizer.recognize_google(audio)
    except sr.UnknownValueError:
        return ""
    except sr.RequestError:
        print("Speech service unavailable.")
        return ""


def ask(system, history, max_tokens=1000):
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=history,
    )
    return "".join(b.text for b in response.content if b.type == "text")


def save_message(role, content):
    db.execute(
        "INSERT INTO messages (created, role, content) VALUES (?, ?, ?)",
        (now(), role, content),
    )
    db.commit()


PERSONA_TAG = re.compile(r"\[\[NEW_PERSONA:\s*(.+?)\s*\|\s*(.+?)\s*\]\]", re.DOTALL)


def handle_persona_tag(reply):
    # Saves any new persona the model created, and removes the tag from what is spoken.
    for name, desc in PERSONA_TAG.findall(reply):
        db.execute(
            "INSERT OR REPLACE INTO personas (name, description) VALUES (?, ?)",
            (name.strip().lower(), desc.strip()),
        )
        db.commit()
        print(f"[Saved new persona: {name.strip()}]")
    return PERSONA_TAG.sub("", reply).strip()


def save_summary(history):
    if not history:
        return
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in history)
    prompt = (
        "Below is a conversation between Dheeraj and his friend.\n"
        "Write brief notes the friend should remember next time:\n"
        "1) one or two sentences on how he was feeling and what he talked about,\n"
        "2) any durable facts, goals or decisions he stated, one per line.\n"
        "Only include what he actually said. Do not guess or diagnose.\n\n"
        + transcript
    )
    summary = ask(
        "You write short, factual notes.",
        [{"role": "user", "content": prompt}],
        max_tokens=500,
    )
    db.execute(
        "INSERT INTO notes (created, kind, content) VALUES (?, ?, ?)",
        (now(), "conversation", summary.strip()),
    )
    db.commit()


system_prompt = build_system_prompt()
history = []

speak("Hey Dheeraj, I'm here. Say goodbye whenever you want to stop.")

try:
    while True:
        user_text = listen()
        if not user_text:
            continue
        print("You:", user_text)
        if "goodbye" in user_text.lower():
            break
        history.append({"role": "user", "content": user_text})
        save_message("user", user_text)
        reply = ask(system_prompt, history)
        spoken = handle_persona_tag(reply)
        # A new persona is available right away in this same conversation.
        system_prompt = build_system_prompt()
        history.append({"role": "assistant", "content": spoken})
        save_message("assistant", spoken)
        print("Friend:", spoken)
        speak(spoken)
except KeyboardInterrupt:
    print("\nStopping.")

print("Saving notes...")
save_summary(history)
speak("Goodbye Dheeraj, talk soon.")

