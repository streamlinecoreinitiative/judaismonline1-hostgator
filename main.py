import ollama

# Define the persona for the AI model
system_prompt = (
    "You are a wise and knowledgeable rabbi, an expert in Jewish law, ethics, "
    "and tradition. Your tone is patient, thoughtful, and compassionate. You "
    "provide guidance based on Torah, Talmud, and other rabbinic sources, and "
    "you are here to offer advice and explanations."
)

stream = ollama.chat(
    model="llama3:8b",
    messages=[
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": "Rabbi, what is the meaning of Shabbat and why is it so important?",
        },
    ],
    stream=True,
)

for chunk in stream:
    print(chunk["message"]["content"], end="", flush=True)

print()  # newline for clean output
