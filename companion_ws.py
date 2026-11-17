import re
import sqlite3
import subprocess
import threading
import time
from datetime import datetime

import anthropic
import speech_recognition as sr
from tavily import TavilyClient

MODEL = "claude-sonnet-5-5"

client = anthropic.Anthropic()
tavily = TavilyClient()
recognizer = sr.Recognizer()
recognizer.pause_threshold = 1.8

SEARCH_TOOL = {
    "name": "web_search",
    "description": (
        "Search the web for current information, such as news, job market "
        "trends, companies, prices or facts that may have changed. "
        "Use it only when current or outside information is truly needed."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "A short search query"}
        },
        "required": ["query"],
    },
}

db = sqlite3.connect("memory.db", check_same_thread=False)
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
Keep replies brief, usually two or three sentences, since he can interrupt you.
Use what you remember about him naturally, the way a friend would.
Do not read his notes back to him, and only bring up something old when it fits.
You always start as his friend. When he brings up a topic, you can shift into the
right role below, and shift back when the topic changes.
If his message looks cut off or is only a few words, he may have interrupted you.
Just listen and respond to what he actually said.
You can search the web when you need current information. When you use it, say what you found in two or three short spoken sentences, and mention where it came from. Never read out web addresses."""

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


def run_search(query):
    print(f"[Searching: {query}]")
    try:
        result = tavily.search(query=query, max_results=4)
    except Exception as error:
        return f"Search failed: {error}"
    parts = []
    for item in result.get("results", []):
        parts.append(f"{item['title']}: {item['content'][:400]}")
    return "\n".join(parts) or "No results found."


def ask(system, history, max_tokens=1000, use_search=True):
    tools = [SEARCH_TOOL] if use_search else []
    messages = list(history)
    for _ in range(3):
        kwargs = dict(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        if tools:
            kwargs["tools"] = tools
        response = client.messages.create(**kwargs)
        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text")
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type == "tool_use":
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": run_search(block.input.get("query", "")),
                    }
                )
        messages.append({"role": "user", "content": results})
    return "Sorry, I could not finish that search. Let's try again."


def save_message(role, content):
    db.execute(
        "INSERT INTO messages (created, role, content) VALUES (?, ?, ?)",
        (now(), role, content),
    )
    db.commit()


PERSONA_TAG = re.compile(r"\[\[NEW_PERSONA:\s*(.+?)\s*\|\s*(.+?)\s*\]\]", re.DOTALL)


def handle_persona_tag(reply):
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
        use_search=False,
    )
    db.execute(
        "INSERT INTO notes (created, kind, content) VALUES (?, ?, ?)",
        (now(), "conversation", summary.strip()),
    )
    db.commit()


# ---------- Barge-in speaking ----------

captured = {"audio": None}


def split_sentences(text):
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


def speak_interruptible(text, interrupted):
    for sentence in split_sentences(text):
        if interrupted.is_set():
            return
        proc = subprocess.Popen(["say", sentence])
        while proc.poll() is None:
            if interrupted.is_set():
                proc.terminate()
                return
            time.sleep(0.03)


def speak_plain(text):
    subprocess.run(["say", text])


def listen_for_interrupt(interrupted, stop_flag):
    mic = sr.Microphone()
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.3)
        while not stop_flag.is_set():
            try:
                audio = recognizer.listen(
                    source, timeout=0.5, phrase_time_limit=30
                )
            except sr.WaitTimeoutError:
                continue
            interrupted.set()
            captured["audio"] = audio
            return


def transcribe(audio):
    try:
        return recognizer.recognize_google(audio)
    except sr.UnknownValueError:
        return ""
    except sr.RequestError:
        print("Speech service unavailable.")
        return ""


def listen_normal():
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.4)
        print("Listening...")
        audio = recognizer.listen(source, phrase_time_limit=30)
    return transcribe(audio)


def speak_with_barge_in(text):
    interrupted = threading.Event()
    stop_flag = threading.Event()
    captured["audio"] = None
    listener = threading.Thread(
        target=listen_for_interrupt, args=(interrupted, stop_flag), daemon=True
    )
    listener.start()
    speak_interruptible(text, interrupted)
    stop_flag.set()
    listener.join(timeout=2)
    if interrupted.is_set() and captured["audio"] is not None:
        return transcribe(captured["audio"])
    return ""


system_prompt = build_system_prompt()
history = []

speak_plain("Hey Dheeraj, I'm here. Say goodbye whenever you want to stop.")

try:
    pending = ""
    while True:
        user_text = pending or listen_normal()
        pending = ""
        if not user_text:
            continue
        print("You:", user_text)
        if "goodbye" in user_text.lower():
            break
        history.append({"role": "user", "content": user_text})
        save_message("user", user_text)
        reply = ask(system_prompt, history)
        spoken = handle_persona_tag(reply)
        system_prompt = build_system_prompt()
        history.append({"role": "assistant", "content": spoken})
        save_message("assistant", spoken)
        print("Friend:", spoken)
        pending = speak_with_barge_in(spoken)
except KeyboardInterrupt:
    print("\nStopping.")

print("Saving notes...")
save_summary(history)
speak_plain("Goodbye Dheeraj, talk soon.")
