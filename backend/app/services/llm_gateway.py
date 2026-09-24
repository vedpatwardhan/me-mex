import os
import re
import json
import httpx
from typing import List, Dict, Any, Optional

# Configuration for vLLM Server on Colab / Remote
COLAB_VLLM_URL = os.getenv("COLAB_VLLM_URL", "http://localhost:8000/v1")
MODEL_NAME = os.getenv("LLM_MODEL_NAME", "mistralai/Ministral-3b-instruct")

# Official Reasoning System Prompt Template for Ministral-3B-Reasoning
OFFICIAL_REASONING_SYSTEM_PROMPT = """# HOW YOU SHOULD THINK AND ANSWER
First draft your thinking process (inner monologue) until you arrive at a response. Format your response using Markdown, and use LaTeX for any mathematical equations. Write both your thoughts and the response in the same language as the input. Your thinking process must follow the template below:

[THINK]
Your thoughts or/and draft, like working through an exercise on scratch paper. Be as casual and as long as you want until you are confident to generate the response to the user.
[/THINK]

Here, provide a self-contained response."""


class LLMGateway:
    """Gateway for querying Ministral 3-8B Reasoning running on vLLM Colab instance with structured reasoning support."""

    def __init__(self, base_url: str = COLAB_VLLM_URL, model: str = MODEL_NAME):
        self.base_url = base_url.rstrip("/")
        self.model = model
        headers = {
            "ngrok-skip-browser-warning": "true",
            "Bypass-Tunnel-Reminder": "true",
            "User-Agent": "Me-Mex-Client",
        }
        self.client = httpx.Client(timeout=60.0, headers=headers)

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

    def generate_chat_completion(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        top_p: float = 0.95,
    ) -> str:
        """Call vLLM OpenAI-compatible endpoint with automatic reasoning prompt formatting & output parsing."""
        url = f"{self.base_url}/chat/completions"
        formatted_messages = self.prepare_reasoning_messages(messages)

        payload = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
        }
        try:
            resp = self.client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                raw_content = data["choices"][0]["message"]["content"]
                parsed = self.parse_reasoning_output(raw_content)
                if parsed["thinking"]:
                    print(
                        f"[LLMGateway] Reasoning Tokens Generated: {len(parsed['thinking'])} chars"
                    )
                return parsed["final_response"]
            else:
                print(
                    f"[LLMGateway] HTTP error {resp.status_code}: {resp.text}. Using synthetic fallback."
                )
                return self._rule_based_fallback(messages)
        except Exception as e:
            print(
                f"[LLMGateway] Network/Connection error ({e}). Using synthetic fallback response."
            )
            return self._rule_based_fallback(messages)

    def _rule_based_fallback(self, messages: List[Dict[str, Any]]) -> str:
        """Synthetic structured responses for local testing when Colab vLLM server is disconnected."""
        user_msg = next(
            (
                m["content"]
                for m in reversed(messages)
                if m.get("role") == "user" and isinstance(m.get("content"), str)
            ),
            "",
        )
        last_prompt = user_msg.lower()

        if "intent" in last_prompt or "classify" in last_prompt:
            query_part = (
                last_prompt.split('user input: "')[-1].split('"')[0]
                if 'user input: "' in last_prompt
                else last_prompt
            )
            if (
                "http" in query_part
                or "arxiv" in query_part
                or "ingest" in query_part
                or "paper abstract" in query_part
            ):
                return json.dumps({"intent": "DOCUMENT_INGESTION"})
            elif any(
                k in query_part
                for k in [
                    "compare",
                    "synthesize",
                    "explain",
                    "concept",
                    "department",
                    "graph",
                    "paper",
                    "models",
                    "retrieval",
                    "search",
                    "latent",
                ]
            ):
                return json.dumps({"intent": "GRAPH_RETRIEVAL"})
            return json.dumps({"intent": "DIRECT_CONVERSATION"})

        if "department" in last_prompt or "community" in last_prompt:
            return json.dumps(
                {
                    "department_name": "World Models & Latent Dynamics",
                    "summary": "Focuses on latent space trajectory rollouts, predictive representation learning (JEPA), and MPC planning efficiency over pixel prediction.",
                }
            )
        elif "extract" in last_prompt or "candidate" in last_prompt:
            return json.dumps(
                {
                    "concepts": [
                        {
                            "title": "Joint-Embedding Predictive Architecture (JEPA)",
                            "description": "Predicts representation in latent space without pixel reconstruction.",
                        },
                        {
                            "title": "Latent MPC Planning",
                            "description": "Generates 100x speedup in action sequence optimization.",
                        },
                    ],
                    "edges": [
                        {
                            "source": "Joint-Embedding Predictive Architecture (JEPA)",
                            "target": "Latent MPC Planning",
                            "relation": "BUILDS_UPON",
                            "body": "JEPA latent rollouts feed directly into MPC action search.",
                        }
                    ],
                }
            )
        elif "synthesize" in last_prompt or "executive" in last_prompt:
            return "Executive Synthesis: Latent-space world models (JEPA) supersede older pixel-space generators for robotic action planning due to 100x computational efficiency."
        else:
            return "Local vLLM Gateway Mock Response: Processing input successfully."


llm_gateway = LLMGateway()
