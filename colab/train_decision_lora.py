#!/usr/bin/env python3
"""
SFT fine-tune LoRA on Ministral 3 8B Instruct for decision relevance JSON.

Usage (Colab, after uploading train.jsonl / val.jsonl):

  python train_decision_lora.py \
    --train /content/train.jsonl \
    --val /content/val.jsonl \
    --output /content/decision-lora

Requires: torch, transformers, peft, datasets, accelerate (see requirements-colab.txt).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if _BACKEND.is_dir():
    sys.path.insert(0, str(_BACKEND))

from app.bootstrap.decision_prompt import (  # noqa: E402
    build_decision_prompt,
    format_assistant_relevance,
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def row_to_messages(row: dict[str, Any], *, rng: random.Random) -> list[dict[str, str]]:
    frontier = list(row["frontier"])
    labels = dict(row["label_relevance"])
    indices = list(range(len(frontier)))
    rng.shuffle(indices)
    frontier = [frontier[i] for i in indices]
    shuffled_labels = {
        frontier[i]["id"]: labels.get(frontier[i]["id"], 0.0)
        for i in range(len(frontier))
    }
    user = build_decision_prompt(row["query_node"], frontier)
    assistant = format_assistant_relevance(shuffled_labels)
    return [
        {"role": "user", "content": user},
        {"role": "assistant", "content": assistant},
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--val", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=Path("/content/decision-lora"))
    parser.add_argument(
        "--base-model", default="mistralai/Ministral-3-8B-Instruct-2512"
    )
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--lora-r", type=int, default=32)
    parser.add_argument("--lora-alpha", type=int, default=64)
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    import torch
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
    from trl import SFTTrainer

    rng = random.Random(args.seed)
    train_rows = load_jsonl(args.train)

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    def to_text(messages: list[dict[str, str]]) -> str:
        return tokenizer.apply_chat_template(messages, tokenize=False)

    texts = [to_text(row_to_messages(r, rng=rng)) for r in train_rows]
    train_ds = Dataset.from_dict({"text": texts})

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
        device_map="auto",
    )
    lora = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    )
    model = get_peft_model(model, lora)

    training_args = TrainingArguments(
        output_dir=str(args.output / "checkpoints"),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        logging_steps=10,
        save_strategy="epoch",
        bf16=torch.cuda.is_bf16_supported(),
        fp16=not torch.cuda.is_bf16_supported(),
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        dataset_text_field="text",
        max_seq_length=args.max_length,
        tokenizer=tokenizer,
    )
    trainer.train()
    args.output.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.output)
    tokenizer.save_pretrained(args.output)
    print(f"Saved adapter to {args.output}")


if __name__ == "__main__":
    main()
