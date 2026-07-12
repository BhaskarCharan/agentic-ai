"""The LinkedIn specialist - same shape and reasoning as `gmail_agent.py`,
second toolkit. See that file's docstring for why this is lazily built
(`@lru_cache`) rather than a module-level constant.
"""

from functools import lru_cache

from langchain.agents import create_agent

from app.agent.linkedin_tools import get_linkedin_tools
from app.agent.llm import get_llm


@lru_cache
def get_linkedin_agent():
    return create_agent(get_llm(), get_linkedin_tools(), name="linkedin_agent")
