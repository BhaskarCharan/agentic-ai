"""
Tools the agent is allowed to call.

Right now there's exactly one: `multiply`. LangChain's `@tool` decorator
turns a plain typed function into a schema the LLM can see and call - the
function's docstring becomes the tool description the model reads to decide
*when* to use it, and the type hints become its JSON-schema arguments.
"""

from langchain_core.tools import tool


@tool
def multiply(a: float, b: float) -> float:
    """Multiply two numbers together and return the product.

    Use this whenever the user asks for a multiplication, even for simple
    numbers - always call the tool rather than computing it yourself.
    """
    return a * b


# All tools the agent has access to. New tools just get added to this list -
# graph.py binds whatever is here to the LLM, nothing else needs to change.
TOOLS = [multiply]
