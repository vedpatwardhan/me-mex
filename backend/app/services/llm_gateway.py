import os
import re
import json
import time
import httpx
from typing import List, Dict, Any, Optional, Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

from app.config import settings
from app.services.logger import logger, console
from app.services.llm_tracer import llm_tracer

# Configuration for vLLM Server on Colab / Remote
COLAB_VLLM_URL = settings.COLAB_VLLM_URL
MODEL_NAME = settings.LLM_MODEL_NAME

# Official Reasoning System Prompt Template for Ministral-3B-Reasoning
OFFICIAL_REASONING_SYSTEM_PROMPT = """# HOW YOU SHOULD THINK AND ANSWER
First draft your thinking process (inner monologue) until you arrive at a response. Format your response using Markdown, and use LaTeX for any mathematical equations. Write both your thoughts and the response in the same language as the input. NEVER use emojis, emoticons, or decorative unicode symbols anywhere in the response. Your thinking process must follow the template below:

[THINK]
Your thoughts or/and draft, like working through an exercise on scratch paper. Be as casual and as long as you want until you are confident to generate the response to the user.
[/THINK]

Here, provide a self-contained response without any emojis."""


EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # misc symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F700-\U0001F77F"  # alchemical symbols
    "\U0001F780-\U0001F7FF"  # geometric shapes extended
    "\U0001F800-\U0001F8FF"  # supplemental arrows-c
    "\U0001F900-\U0001F9FF"  # supplemental symbols and pictographs
    "\U0001FA00-\U0001FA6F"  # chess symbols
    "\U0001FA70-\U0001FAFF"  # symbols and pictographs extended-a
    "\U00002600-\U000026FF"  # misc symbols
    "\U00002700-\U000027BF"  # dingbats
    "]+",
    flags=re.UNICODE,
)


def strip_emojis(text: str) -> str:
    """Removes all unicode emojis and pictographs to prevent TTS verbalization artifacts."""
    if not text:
        return text
    return EMOJI_PATTERN.sub("", text)


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
        self.client = httpx.Client(timeout=timeout, headers=headers, trust_env=False)

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
            # We perform a minimal POST to /chat/completions or GET to /models
            resp = self.client.get(f"{self.base_url}/models", timeout=5.0)
            if resp.status_code == 200:
                return True
            # Fallback check via chat completions if /models is forbidden by tunnel proxy
            resp_post = self.client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
                timeout=5.0,
            )
            return resp_post.status_code == 200
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
        caller: Optional[str] = None,
        trace: bool = True,
    ) -> str:
        """Call vLLM OpenAI-compatible endpoint with optional reasoning prompt formatting & structured output decoding."""
        start_time = time.perf_counter()
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
            # Enable stream=True under the hood so vLLM immediately yields tokens as Server-Sent Events.
            # This continuously streams bytes across Cloudflare / reverse proxy tunnels, preventing
            # the Cloudflare Error 524 (100-second idle socket timeout) on large generations.
            payload["stream"] = True
            collected_chunks: List[str] = []
            collected_reasoning: List[str] = []

            with self.client.stream("POST", url, json=payload) as resp:
                if resp.status_code != 200:
                    err_bytes = resp.read()
                    err_detail = f"vLLM Server returned HTTP {resp.status_code}: {err_bytes.decode('utf-8', errors='ignore')}"
                    print(f"[LLMGateway ERROR] {err_detail}")
                    raise ConnectionError(err_detail)

                for line in resp.iter_lines():
                    line = line.strip()
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            chunk = json.loads(data_str)
                            choices = chunk.get("choices", [])
                            if not choices:
                                continue
                            delta = choices[0].get("delta", {})
                            c_piece = delta.get("content")
                            if c_piece:
                                collected_chunks.append(c_piece)
                            r_piece = delta.get("reasoning_content") or delta.get(
                                "reasoning"
                            )
                            if r_piece:
                                collected_reasoning.append(r_piece)
                        except json.JSONDecodeError:
                            continue

            raw_content = "".join(collected_chunks)
            vllm_reasoning = "".join(collected_reasoning)

            if vllm_reasoning:
                console.print(
                    f"      [dim]🧠 Model reasoning trace generated: {len(vllm_reasoning)} chars[/dim]"
                )
            elif enable_reasoning:
                parsed = self.parse_reasoning_output(raw_content)
                if parsed["thinking"]:
                    console.print(
                        f"      [dim]🧠 Parsed [THINK] reasoning trace: {len(parsed['thinking'])} chars[/dim]"
                    )

            final_text = ""
            if vllm_reasoning:
                final_text = strip_emojis(raw_content.strip())
            elif enable_reasoning:
                parsed = self.parse_reasoning_output(raw_content)
                final_text = strip_emojis(parsed["final_response"])
            else:
                final_text = strip_emojis(raw_content.strip())

            elapsed = time.perf_counter() - start_time
            if trace:
                llm_tracer.log_call(
                    caller=caller,
                    model=self.model,
                    messages=messages,
                    duration_seconds=elapsed,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_raw=raw_content,
                    response_parsed=final_text,
                    status="SUCCESS",
                )

            return final_text
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            if trace:
                llm_tracer.log_call(
                    caller=caller,
                    model=self.model,
                    messages=messages,
                    duration_seconds=elapsed,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    status="FAILED",
                    error=str(e),
                )
            logger.error_box("LLMGateway Request Failed", str(e))
            raise ConnectionError(f"vLLM Server unreachable or error ({e})")

    def generate_structured_completion(
        self,
        messages: List[Dict[str, Any]],
        response_model: Type[T],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        max_retries: int = 2,
        enable_reasoning: bool = False,
        caller: Optional[str] = None,
    ) -> T:
        """Invokes LLM with strict JSON Schema constraints and validates output against response_model.

        Leverages OpenAI-compatible response_format and vLLM guided_json for grammar-constrained decoding.
        Implements an automatic 2-attempt retry loop on JSON validation or parse failures.
        """
        start_time = time.perf_counter()
        schema = response_model.model_json_schema()
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": response_model.__name__,
                "strict": True,
                "schema": schema,
            },
        }

        last_error = None
        raw_res = None
        for attempt in range(1, max_retries + 1):
            try:
                raw_res = self.generate_chat_completion(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                    guided_json=schema,
                    enable_reasoning=enable_reasoning,
                    trace=False,
                )
                validated_model = response_model.model_validate_json(raw_res)
                elapsed = time.perf_counter() - start_time
                llm_tracer.log_call(
                    caller=caller,
                    model=self.model,
                    messages=messages,
                    duration_seconds=elapsed,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_raw=raw_res,
                    response_parsed=validated_model.model_dump(),
                    response_model_name=response_model.__name__,
                    attempts=attempt,
                    status="SUCCESS",
                )
                return validated_model
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    print(
                        f"[LLMGateway] Structured generation for {response_model.__name__} failed ({e}). "
                        f"Retrying (attempt {attempt + 1}/{max_retries})..."
                    )
                    continue
                print(
                    f"[LLMGateway ERROR] Structured completion for {response_model.__name__} failed after "
                    f"{max_retries} attempts: {last_error}"
                )
                elapsed = time.perf_counter() - start_time
                llm_tracer.log_call(
                    caller=caller,
                    model=self.model,
                    messages=messages,
                    duration_seconds=elapsed,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_raw=raw_res,
                    response_model_name=response_model.__name__,
                    attempts=attempt,
                    status="FAILED",
                    error=str(last_error),
                )
                raise RuntimeError(
                    f"Structured completion failed for {response_model.__name__} after {max_retries} attempts: {last_error}"
                ) from last_error

    async def stream_chat_completion(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        top_p: float = 0.95,
        enable_reasoning: bool = False,
        caller: Optional[str] = None,
    ):
        """Asynchronously stream response tokens from vLLM, yielding clean sanitized deltas."""
        start_time = time.perf_counter()
        url = f"{self.base_url}/chat/completions"
        formatted_messages = (
            self.prepare_reasoning_messages(messages) if enable_reasoning else messages
        )

        payload = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "stream": True,
        }

        headers = {
            "ngrok-skip-browser-warning": "true",
            "Bypass-Tunnel-Reminder": "true",
            "User-Agent": "Me-Mex-Client",
        }

        collected_tokens = []
        try:
            async with httpx.AsyncClient(
                timeout=60.0, headers=headers, trust_env=False
            ) as client:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        raise ConnectionError(
                            f"vLLM stream error {response.status_code}: {error_text.decode('utf-8', errors='ignore')}"
                        )

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or line == "data: [DONE]":
                            continue
                        if line.startswith("data: "):
                            data_str = line[6:]
                            try:
                                chunk = json.loads(data_str)
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    sanitized = strip_emojis(content)
                                    if sanitized:
                                        collected_tokens.append(sanitized)
                                        yield sanitized
                            except json.JSONDecodeError:
                                pass

            elapsed = time.perf_counter() - start_time
            full_response = "".join(collected_tokens)
            llm_tracer.log_call(
                caller=caller,
                model=self.model,
                messages=messages,
                duration_seconds=elapsed,
                temperature=temperature,
                max_tokens=max_tokens,
                response_raw=full_response,
                response_parsed=full_response,
                status="SUCCESS",
            )
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            llm_tracer.log_call(
                caller=caller,
                model=self.model,
                messages=messages,
                duration_seconds=elapsed,
                temperature=temperature,
                max_tokens=max_tokens,
                status="FAILED",
                error=str(e),
            )
            raise


llm_gateway = LLMGateway()
