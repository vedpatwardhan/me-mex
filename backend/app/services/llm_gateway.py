import json
import re
import time
from collections.abc import AsyncIterator, Callable
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

import logging

from app.colab_urls import colab_inference_base_url
from app.config import settings
from app.services.llm_tracer import llm_tracer

_log = logging.getLogger(__name__)

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
    "\U0001f600-\U0001f64f"  # emoticons
    "\U0001f300-\U0001f5ff"  # misc symbols & pictographs
    "\U0001f680-\U0001f6ff"  # transport & map symbols
    "\U0001f700-\U0001f77f"  # alchemical symbols
    "\U0001f780-\U0001f7ff"  # geometric shapes extended
    "\U0001f800-\U0001f8ff"  # supplemental arrows-c
    "\U0001f900-\U0001f9ff"  # supplemental symbols and pictographs
    "\U0001fa00-\U0001fa6f"  # chess symbols
    "\U0001fa70-\U0001faff"  # symbols and pictographs extended-a
    "\U00002600-\U000026ff"  # misc symbols
    "\U00002700-\U000027bf"  # dingbats
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
        base_url: str | None = None,
        model: str = MODEL_NAME,
        timeout: float = settings.LLM_TIMEOUT,
    ):
        self.base_url = (base_url or settings.colab_vllm_api_base).rstrip("/")
        self.model = model
        headers = {
            "ngrok-skip-browser-warning": "true",
            "Bypass-Tunnel-Reminder": "true",
            "User-Agent": "Me-Mex-Client",
        }
        limits = httpx.Limits(
            max_connections=settings.HTTPX_MAX_CONNECTIONS,
            max_keepalive_connections=settings.HTTPX_MAX_KEEPALIVE,
        )
        self.client = httpx.Client(
            timeout=timeout,
            headers=headers,
            trust_env=False,
            limits=limits,
        )

    def prepare_reasoning_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
                if isinstance(existing_content, str) and "[THINK]" not in existing_content:
                    combined_content = f"{OFFICIAL_REASONING_SYSTEM_PROMPT}\n\nAdditional Instructions:\n{existing_content}"
                    formatted_messages.append({"role": "system", "content": combined_content})
                else:
                    formatted_messages.append(m)
            else:
                formatted_messages.append(m)

        return formatted_messages

    def parse_reasoning_output(self, content: str) -> dict[str, str]:
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
        except httpx.HTTPError:
            return False

    def generate_chat_completion(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 8192,
        top_p: float = 0.95,
        response_format: dict[str, Any] | None = None,
        guided_json: dict[str, Any] | None = None,
        enable_reasoning: bool = True,
        caller: str | None = None,
        trace: bool = True,
    ) -> str:
        """Call vLLM OpenAI-compatible endpoint with optional reasoning prompt formatting & structured output decoding."""
        start_time = time.perf_counter()
        url = f"{self.base_url}/chat/completions"
        formatted_messages = (
            self.prepare_reasoning_messages(messages) if enable_reasoning else messages
        )

        payload: dict[str, Any] = {
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
            collected_chunks: list[str] = []
            collected_reasoning: list[str] = []

            with self.client.stream("POST", url, json=payload) as resp:
                if resp.status_code != 200:
                    err_bytes = resp.read()
                    err_detail = f"vLLM Server returned HTTP {resp.status_code}: {err_bytes.decode('utf-8', errors='ignore')}"
                    _log.error("%s", err_detail)
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
                            r_piece = delta.get("reasoning_content") or delta.get("reasoning")
                            if r_piece:
                                collected_reasoning.append(r_piece)
                        except json.JSONDecodeError:
                            continue

            raw_content = "".join(collected_chunks)
            vllm_reasoning = "".join(collected_reasoning)

            if vllm_reasoning:
                _log.debug("Model reasoning trace: %s chars", len(vllm_reasoning))
            elif enable_reasoning:
                parsed = self.parse_reasoning_output(raw_content)
                if parsed["thinking"]:
                    _log.debug(
                        "Parsed [THINK] reasoning trace: %s chars",
                        len(parsed["thinking"]),
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
        except (httpx.HTTPError, ConnectionError, OSError) as e:
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
            _log.error("LLMGateway request failed: %s", e)
            raise ConnectionError(f"vLLM Server unreachable or error ({e})") from e

    def generate_structured_completion(
        self,
        messages: list[dict[str, Any]],
        response_model: type[T],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        max_retries: int = 2,
        enable_reasoning: bool = False,
        caller: str | None = None,
        payload_mutator: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
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
        attempt_messages: list[dict[str, Any]] = list(messages)
        for attempt in range(1, max_retries + 1):
            try:
                raw_res = self.generate_chat_completion(
                    messages=attempt_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                    guided_json=schema,
                    enable_reasoning=enable_reasoning,
                    trace=False,
                )
                if payload_mutator is not None:
                    parsed_payload = json.loads(raw_res)
                    parsed_payload = payload_mutator(parsed_payload)
                    validated_model = response_model.model_validate(parsed_payload)
                else:
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
            except (ValueError, ConnectionError, httpx.HTTPError, json.JSONDecodeError) as e:
                last_error = e
                if attempt < max_retries:
                    _log.warning(
                        "Structured generation for %s failed (%s). Retrying (%d/%d)...",
                        response_model.__name__,
                        e,
                        attempt + 1,
                        max_retries,
                    )
                    attempt_messages = attempt_messages + [
                        {
                            "role": "user",
                            "content": (
                                "Your JSON failed schema validation. Fix every error and return "
                                "a complete response.\nErrors:\n- " + str(e)
                            ),
                        }
                    ]
                    continue
                _log.error(
                    "Structured completion for %s failed after %d attempts: %s",
                    response_model.__name__,
                    max_retries,
                    last_error,
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
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        top_p: float = 0.95,
        enable_reasoning: bool = False,
        caller: str | None = None,
    ):
        """Asynchronously stream response tokens from vLLM, yielding clean sanitized deltas."""
        start_time = time.perf_counter()
        completion_cap = (
            max_tokens if max_tokens is not None else settings.LLM_COMPLETION_MAX_TOKENS
        )
        url = f"{self.base_url}/chat/completions"
        formatted_messages = (
            self.prepare_reasoning_messages(messages) if enable_reasoning else messages
        )

        payload = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": completion_cap,
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
            stream_timeout = max(60.0, float(settings.LLM_TIMEOUT))
            async with (
                httpx.AsyncClient(
                    timeout=stream_timeout, headers=headers, trust_env=False
                ) as client,
                client.stream("POST", url, json=payload) as response,
            ):
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
                max_tokens=completion_cap,
                response_raw=full_response,
                response_parsed=full_response,
                status="SUCCESS",
            )
        except (httpx.HTTPError, ConnectionError, OSError) as e:
            elapsed = time.perf_counter() - start_time
            llm_tracer.log_call(
                caller=caller,
                model=self.model,
                messages=messages,
                duration_seconds=elapsed,
                temperature=temperature,
                max_tokens=completion_cap,
                status="FAILED",
                error=str(e),
            )
            raise

    async def stream_voice_speak(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        top_p: float = 0.95,
        caller: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream interleaved token and audio events from Colab /v1/voice/speak."""
        start_time = time.perf_counter()
        completion_cap = (
            max_tokens if max_tokens is not None else settings.LLM_COMPLETION_MAX_TOKENS
        )
        base = colab_inference_base_url().rstrip("/")
        url = f"{base}/v1/voice/speak"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": completion_cap,
            "top_p": top_p,
        }
        headers = {
            "ngrok-skip-browser-warning": "true",
            "Bypass-Tunnel-Reminder": "true",
            "User-Agent": "Me-Mex-Client",
        }
        collected_tokens: list[str] = []
        try:
            stream_timeout = max(60.0, float(settings.LLM_TIMEOUT))
            async with (
                httpx.AsyncClient(
                    timeout=stream_timeout, headers=headers, trust_env=False
                ) as client,
                client.stream("POST", url, json=payload) as response,
            ):
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise ConnectionError(
                        f"voice/speak error {response.status_code}: "
                        f"{error_text.decode('utf-8', errors='ignore')}"
                    )

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or line == "data: [DONE]":
                        continue
                    if not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    etype = event.get("type")
                    if etype == "token":
                        content = strip_emojis(str(event.get("content") or ""))
                        if content:
                            collected_tokens.append(content)
                            yield {"kind": "token", "content": content}
                    elif etype == "audio":
                        data = event.get("data")
                        if data:
                            yield {
                                "kind": "audio",
                                "format": event.get("format") or "wav",
                                "data": data,
                            }
                    elif etype == "error":
                        raise ConnectionError(str(event.get("message") or "voice/speak error"))

            elapsed = time.perf_counter() - start_time
            llm_tracer.log_call(
                caller=caller,
                model=self.model,
                messages=messages,
                duration_seconds=elapsed,
                temperature=temperature,
                max_tokens=completion_cap,
                response_raw="".join(collected_tokens),
                response_parsed="".join(collected_tokens),
                status="SUCCESS",
            )
        except (httpx.HTTPError, ConnectionError, OSError) as e:
            elapsed = time.perf_counter() - start_time
            llm_tracer.log_call(
                caller=caller,
                model=self.model,
                messages=messages,
                duration_seconds=elapsed,
                temperature=temperature,
                max_tokens=completion_cap,
                status="FAILED",
                error=str(e),
            )
            raise


llm_gateway = LLMGateway()
