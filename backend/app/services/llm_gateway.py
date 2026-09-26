import os
import re
import json
import httpx
from typing import List, Dict, Any, Optional

from app.config import settings

# Configuration for vLLM Server on Colab / Remote
COLAB_VLLM_URL = settings.COLAB_VLLM_URL
MODEL_NAME = settings.LLM_MODEL_NAME

# Official Reasoning System Prompt Template for Ministral-3B-Reasoning
OFFICIAL_REASONING_SYSTEM_PROMPT = """# HOW YOU SHOULD THINK AND ANSWER
First draft your thinking process (inner monologue) until you arrive at a response. Format your response using Markdown, and use LaTeX for any mathematical equations. Write both your thoughts and the response in the same language as the input. Your thinking process must follow the template below:

[THINK]
Your thoughts or/and draft, like working through an exercise on scratch paper. Be as casual and as long as you want until you are confident to generate the response to the user.
[/THINK]

Here, provide a self-contained response."""


class LLMGateway:
    """Gateway for querying Ministral 3-8B Reasoning running on vLLM Colab instance with structured reasoning support."""

    def __init__(
        self,
        base_url: str = COLAB_VLLM_URL,
        model: str = MODEL_NAME,
        timeout: float = settings.LLM_TIMEOUT,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        headers = {
            "ngrok-skip-browser-warning": "true",
            "Bypass-Tunnel-Reminder": "true",
            "User-Agent": "Me-Mex-Client",
        }
        self.client = httpx.Client(timeout=timeout, headers=headers)

    def prepare_reasoning_messages(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Ensures the reasoning system prompt with [THINK] tags is present in message history."""
        has_system = any(m.get("role") == "system" for m in messages)
        formatted_messages = []

        if not has_system:
            system_msg = {
                "role": "system",
                "content": OFFICIAL_REASONING_SYSTEM_PROMPT,
            }
            formatted_messages.append(system_msg)

        for m in messages:
            if m.get("role") == "system":
                existing_content = m.get("content", "")
                if (
                    isinstance(existing_content, str)
                    and "[THINK]" not in existing_content
                ):
                    combined_content = f"{OFFICIAL_REASONING_SYSTEM_PROMPT}\n\nAdditional Instructions:\n{existing_content}"
                    formatted_messages.append(
                        {"role": "system", "content": combined_content}
                    )
                else:
                    formatted_messages.append(m)
            else:
                formatted_messages.append(m)

        return formatted_messages

    def parse_reasoning_output(self, content: str) -> Dict[str, str]:
        """Parses output into reasoning thoughts ([THINK] block) and clean final response."""
        pattern = r"\[THINK\](.*?)\[/THINK\]"
        match = re.search(pattern, content, re.DOTALL)
        if match:
            thinking = match.group(1).strip()
            final_response = re.sub(pattern, "", content, flags=re.DOTALL).strip()
            return {"thinking": thinking, "final_response": final_response}
        return {"thinking": "", "final_response": content.strip()}

    def is_server_available(self) -> bool:
        """Ping vLLM server endpoint to verify live availability."""
        try:
            resp = self.client.get(f"{self.base_url}/models", timeout=2.0)
            return resp.status_code == 200
        except Exception:
            return False

    def generate_chat_completion(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 8192,
        top_p: float = 0.95,
        response_format: Optional[Dict[str, Any]] = None,
        guided_json: Optional[Dict[str, Any]] = None,
        enable_reasoning: bool = True,
    ) -> str:
        """Call vLLM OpenAI-compatible endpoint with optional reasoning prompt formatting & structured output decoding."""
        url = f"{self.base_url}/chat/completions"
        formatted_messages = (
            self.prepare_reasoning_messages(messages) if enable_reasoning else messages
        )

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
        }
        if response_format:
            payload["response_format"] = response_format
        if guided_json:
            payload["guided_json"] = guided_json

        try:
            resp = self.client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                choice = data["choices"][0]
                msg_obj = choice.get("message", {})

                # Extract explicit vLLM reasoning fields if provided
                vllm_reasoning = (
                    msg_obj.get("reasoning_content") or msg_obj.get("reasoning") or ""
                )
                raw_content = msg_obj.get("content", "")

                if vllm_reasoning:
                    print(
                        f"[LLMGateway] vLLM Dedicated Reasoning Tokens Generated: {len(vllm_reasoning)} chars"
                    )
                    return raw_content.strip()

                if enable_reasoning:
                    parsed = self.parse_reasoning_output(raw_content)
                    if parsed["thinking"]:
                        print(
                            f"[LLMGateway] Parsed [THINK] Reasoning Tokens: {len(parsed['thinking'])} chars"
                        )
                    return parsed["final_response"]
                return raw_content.strip()
            else:
                raise ConnectionError(
                    f"vLLM Server returned HTTP {resp.status_code}: {resp.text}"
                )
        except Exception as e:
            raise ConnectionError(f"vLLM Server unreachable or error ({e})")


llm_gateway = LLMGateway()
