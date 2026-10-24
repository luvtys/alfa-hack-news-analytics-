import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(override=True)
client = OpenAI(base_url=os.getenv("OPENAI_BASE_URL"), api_key=os.getenv("OPENAI_API_KEY"))

resp = client.chat.completions.create(
    model="qwen/qwen3.6-35b-a3b",
    messages=[{"role": "user", "content": "Напиши только слово ДА"}],
    max_tokens=50,
    temperature=0.1,
    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    # Если сервер поддерживает — добавь thinking_token_budget
    # thinking_token_budget=50,
)

msg = resp.choices[0].message
print(f"content: {msg.content}")
print(f"reasoning_content: {getattr(msg, 'reasoning_content', 'НЕТ')}")