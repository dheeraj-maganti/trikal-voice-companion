import anthropic

client = anthropic.Anthropic()

SYSTEM_PROMPT = """You are a warm, honest friend talking with Dheeraj.
Speak in short, natural sentences, like a close friend sitting beside him."""

history = []

print("Type 'quit' to stop.")
while True:
    user_text = input("You: ")
    if user_text.strip().lower() == "quit":
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
