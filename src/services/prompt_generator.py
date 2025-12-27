import json
import random
from pathlib import Path
from typing import List, Dict
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import torch


class PromptGenerator:
    def __init__(self):
        self._load_prompt_templates()
        self.model_name = "google/flan-t5-small"
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model.to(self.device)

    def _load_prompt_templates(self):
        config_path = Path(__file__).parent.parent / "config" / "prompt_templates.json"
        with open(config_path, "r", encoding="utf-8") as f:
            self.prompt_groups = json.load(f)

    def generate_templates(self, context: str, num_segments: int = 3) -> Dict:
        context_truncated = context[:1000]
        detected = self._detect_relevant_placeholders(context_truncated)
        
        group = self._select_best_group(detected)
        
        return {
            "prompt": group["segments"][:num_segments],
            "placeholders": group["placeholders"][:num_segments]
        }

    def _detect_relevant_placeholders(self, context: str) -> List[str]:
        prompt = (
            f"What categories describe this document? "
            f"Choose from: topic, industry, region, purpose, department, type, action, process, issue. "
            f"List 3 categories separated by commas: {context[:300]}"
        )
        
        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
            max_length=256,
            truncation=True
        ).to(self.device)

        outputs = self.model.generate(
            **inputs,
            max_new_tokens=20,
            num_beams=2
        )

        result = self.tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
        categories = [c.strip().lower() for c in result.split(',')]
        return categories[:3] if categories else ["topic", "industry", "region"]

    def _select_best_group(self, detected: List[str], top_k: int = 10) -> Dict:
        scored_groups = []
        for group in self.prompt_groups:
            score = sum(1 for p in group["placeholders"] if p in detected)
            scored_groups.append((score, group))
        
        scored_groups.sort(key=lambda x: x[0], reverse=True)
        top_groups = [g for _, g in scored_groups[:top_k]]
        
        return random.choice(top_groups)
