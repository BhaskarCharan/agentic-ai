"""Helpers for reading LangChain message content.

Depending on the provider, `message.content` is sometimes a plain string
and sometimes a list of content blocks (e.g. Gemini returns
`[{"type": "text", "text": "..."}]` instead of a bare string). Every place
that needs the human-readable text of a message should go through
`extract_text` instead of reading `.content` directly, so we don't have to
remember this quirk in more than one place.
"""

from typing import Any


def extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)

    return ""
