import os
import json
import httpx
from typing import List, Dict, Any, Optional

# Configuration for vLLM Server on Colab / Remote
COLAB_VLLM_URL = os.getenv("COLAB_VLLM_URL", "http://localhost:8000/v1")
MODEL_NAME = os.getenv("LLM_MODEL_NAME", "mistralai/Ministral-3b-instruct")


class LLMGateway:
    """Gateway for querying Ministral 3-8B running on vLLM Colab instance with fallback."""

    def __init__(self, base_url: str = COLAB_VLLM_URL, model: str = MODEL_NAME):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = httpx.Client(timeout=30.0)

    def generate_chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1000,
    ) -> str:
        """Call vLLM OpenAI-compatible endpoint with automatic local rule-based fallback."""
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            resp = self.client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
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

    def _rule_based_fallback(self, messages: List[Dict[str, str]]) -> str:
        """Synthetic structured responses for local testing when Colab vLLM server is disconnected."""
        user_msg = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
        )
        last_prompt = user_msg.lower()

        if "intent" in last_prompt or "classify" in last_prompt:
            # Extract actual query string from user input prompt wrapper if present
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
