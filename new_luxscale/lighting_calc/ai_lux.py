"""Optional OpenAI helper (legacy)."""


def ask_ai_lux(place):
    import openai

    prompt = f"What is the recommended average lux level for lighting in a '{place}'?"
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a lighting design expert."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=50,
    )
    text = response["choices"][0]["message"]["content"]
    numbers = [int(s) for s in text.split() if s.isdigit()]
    return numbers[0] if numbers else 300
