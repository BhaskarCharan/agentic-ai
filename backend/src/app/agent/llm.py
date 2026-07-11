"""
LLM factory.

Kept in its own tiny module so the *rest* of the agent code (graph.py) never
imports a provider-specific class directly - it only calls `get_llm()` and
gets back something implementing LangChain's `BaseChatModel` interface
(supports `.bind_tools()`, `.astream()`, etc). Swapping providers later
(OpenAI, Anthropic, a different Gemini model, ...) means changing only this
file, not the graph logic.
"""

from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import settings


def get_llm() -> ChatGoogleGenerativeAI:
    """Build the chat model used by the agent.

    `temperature=0` makes tool-calling more deterministic, which matters
    for a demo agent whose whole job is "reliably call `multiply`".
    """
    return ChatGoogleGenerativeAI(
        model=settings.model_name,
        google_api_key=settings.google_api_key,
        temperature=0,
    )
