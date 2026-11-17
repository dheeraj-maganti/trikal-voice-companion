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
    "created TEXT, "
    "kind TEXT, "
    "content TEXT)"
)
db.execute(
    "CREATE TABLE IF NOT EXISTS messages ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "created TEXT, "
    "role TEXT, "
    "content TEXT)"
)
db.commit()

BASE_PROMPT = """You are a warm, honest friend talking with Dheeraj.
You are speaking out loud, so use short, natural sentences.
No lists, no markdown, no emojis.
Use what you remember about him naturally, the way a friend would.
Do not read his notes back to him, and only bring up something old when it fits."""


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


def speak(text):
    subprocess.run(["say", text])


def listen():
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        print("Listening...")
        audio = recognizer.listen(source, phrase_time_limit=20)
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


system_prompt = BASE_PROMPT + "\n\n" + load_memory()
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
        history.append({"role": "assistant", "content": reply})
        save_message("assistant", reply)
        print("Friend:", reply)
        speak(reply)
except KeyboardInterrupt:
    print("\nStopping.")

print("Saving notes...")
save_summary(history)
speak("Goodbye Dheeraj, talk soon.")
