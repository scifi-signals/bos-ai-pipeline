"""LLM wrappers for Claude (evidence/article) and GPT-4o (fact-checking)."""

from config import (
    ANTHROPIC_API_KEY, OPENAI_API_KEY,
    CLAUDE_MODEL, GPT4O_MODEL,
    CLAUDE_MAX_TOKENS, GPT4O_MAX_TOKENS,
)


def ask_claude(prompt, system_prompt=None, max_tokens=None):
    """Send prompt to Claude for evidence extraction, consensus, and article generation."""
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    kwargs = {
        "model": CLAUDE_MODEL,
        "max_tokens": max_tokens or CLAUDE_MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system_prompt:
        kwargs["system"] = system_prompt

    response = client.messages.create(**kwargs)
    return response.content[0].text


def ask_gpt4o(prompt, system_prompt=None, max_tokens=None):
    """Send prompt to GPT-4o for independent fact-checking."""
    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=GPT4O_MODEL,
        max_tokens=max_tokens or GPT4O_MAX_TOKENS,
        messages=messages,
    )
    return response.choices[0].message.content


if __name__ == "__main__":
    print("Testing Claude...")
    r = ask_claude("Say 'Claude connection working!' and nothing else.")
    print(r)
    print("\nTesting GPT-4o...")
    r = ask_gpt4o("Say 'GPT-4o connection working!' and nothing else.")
    print(r)
