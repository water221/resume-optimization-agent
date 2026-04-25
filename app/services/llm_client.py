import os

from dotenv import load_dotenv
from fastapi import HTTPException
from openai import OpenAI

load_dotenv()


def get_client() -> OpenAI:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing DEEPSEEK_API_KEY in environment variables.")
    return OpenAI(api_key=api_key, base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))


def llm_chat(messages: list[dict[str, str]], temperature: float = 0.2) -> str:
    client = get_client()
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""
