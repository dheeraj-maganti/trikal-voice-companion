import subprocess
import anthropic
import speech_recognition as sr

client = anthropic.Anthropic()
recognizer = sr.Recognizer()

SYSTEM_PROMPT = """You are a warm, honest friend talking with Dheeraj.
You are speaking out loud, so use short, natural sentences.
No lists, no markdown, no emojis."""

history = []


def speak(text):
    # Uses the built-in Mac voice. Free and works offline.
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


speak("Hey Dheeraj, I'm here. Say goodbye whenever you want to stop.")

while True:
    user_text = listen()
    if not user_text:
        continue
    print("You:", user_text)
    if "goodbye" in user_text.lower():
        speak("Goodbye Dheeraj, talk soon.")
        break
    history.append({"role": "user", "content": user_text})
    response = client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=history,
    )
    reply = "".join(b.text for b in response.content if b.type == "text")
    history.append({"role": "assistant", "content": reply})
    print("Friend:", reply)
    speak(reply)
