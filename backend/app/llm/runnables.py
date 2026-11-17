"""LangChain Runnables that call the vLLM gateway (only entry to HTTP LLM)."""

from __future__ import annotations

from typing import Any, TypeVar

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.prompt_values import ChatPromptValue
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel

from app.services.llm_gateway import llm_gateway

T = TypeVar("T", bound=BaseModel)


def _to_openai_messages(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if isinstance(m, SystemMessage):
            out.append({"role": "system", "content": m.content})
        elif isinstance(m, HumanMessage):
            out.append({"role": "user", "content": m.content})
        elif isinstance(m, AIMessage):
            out.append({"role": "assistant", "content": m.content})
    return out


def structured_llm(schema: type[T], *, caller: str, max_tokens: int = 2048) -> Runnable:
    """Prompt template output → validated Pydantic via vLLM guided JSON."""

    def _run(value: ChatPromptValue | dict) -> T:
        if isinstance(value, ChatPromptValue):
            messages = _to_openai_messages(value.to_messages())
        else:
            messages = value.get("messages") or _to_openai_messages(value["messages"])  # type: ignore[arg-type]
        return llm_gateway.generate_structured_completion(
            messages,
            schema,
            max_tokens=max_tokens,
            enable_reasoning=False,
            caller=caller,
        )

    return RunnableLambda(_run)


def chat_llm(*, caller: str, max_tokens: int = 1024) -> Runnable:
    """Prompt template output → assistant text."""

    def _run(value: ChatPromptValue) -> str:
        messages = _to_openai_messages(value.to_messages())
        return llm_gateway.generate_chat_completion(
            messages,
            max_tokens=max_tokens,
            enable_reasoning=False,
            caller=caller,
        )

    return RunnableLambda(_run)
