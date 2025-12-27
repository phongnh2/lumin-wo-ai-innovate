import json
import random
from pathlib import Path
from typing import List, Dict, Tuple
from collections import defaultdict


class FollowUpGenerator:
    def __init__(self, config_path: str = None):
        self._load_config(config_path)
        self._load_prompt_templates()
        self._build_knowledge_graph()

    def _load_config(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "followup_config.json"
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        self.industries = config["industries"]
        self.regions = config["regions"]
        self.doc_types = config["doc_types"]
        self.topics = config["topics"]
        self.relationships = config["relationships"]
        self.query_pools = config["query_pools"]
        self.temporal_options = config["temporal_options"]
        self.practical_options = config["practical_options"]
        self.xref_options = config["xref_options"]
        self.mentioned_concepts = config["mentioned_concepts"]

    def _load_prompt_templates(self):
        config_path = Path(__file__).parent.parent / "config" / "prompt_templates.json"
        with open(config_path, "r", encoding="utf-8") as f:
            self.prompt_groups = json.load(f)

    def _build_knowledge_graph(self):
        self.cooccurrence = defaultdict(lambda: defaultdict(int))
        for group in self.prompt_groups:
            placeholders = group.get("placeholders", [])
            for i, ph1 in enumerate(placeholders):
                for ph2 in placeholders[i+1:]:
                    self.cooccurrence[ph1][ph2] += 1
                    self.cooccurrence[ph2][ph1] += 1

    def generate(self, prompt: str, max_queries: int = 3) -> List[str]:
        entities = self._extract_entities(prompt)
        prompt_lower = prompt.lower()
        mentioned = self._extract_mentioned_concepts(prompt_lower)

        candidates = []
        candidates.extend(self._get_pool_queries(entities, mentioned))
        candidates.extend(self._expand_by_entities(entities, prompt, mentioned))
        candidates.extend(self._context_enhancements(prompt, entities, mentioned))

        general = [q for q in self.query_pools.get('general', [])
                   if not self._is_mentioned(q, mentioned)]
        random.shuffle(general)
        candidates.extend(general[:3])

        valid = [q for q in candidates if self._is_valid(q, prompt)]
        unique = list(dict.fromkeys(valid))
        ranked = self._rank_queries(unique, prompt, entities)

        if len(ranked) > max_queries + 2:
            top_pool = ranked[:max_queries + 3]
            random.shuffle(top_pool)
            ranked = top_pool + ranked[max_queries + 3:]

        diverse = self._select_diverse(ranked, max_queries)
        return diverse

    def _extract_mentioned_concepts(self, prompt_lower: str) -> set:
        concepts = set()

        for s in self.mentioned_concepts["standards"]:
            if s in prompt_lower:
                concepts.add(s)

        for f in self.mentioned_concepts["features"]:
            if f in prompt_lower:
                concepts.add(f)

        for a in self.mentioned_concepts["actions"]:
            if a in prompt_lower:
                concepts.add(a)

        return concepts

    def _is_mentioned(self, query: str, mentioned: set) -> bool:
        query_lower = query.lower()
        for concept in mentioned:
            if concept in query_lower:
                return True
        return False

    def _get_pool_queries(self, entities: Dict, mentioned: set) -> List[str]:
        queries = []

        if 'industry' in entities:
            pool_key = f"industry_{entities['industry']}"
            pool = self.query_pools.get(pool_key, [])
            filtered = [q for q in pool if not self._is_mentioned(q, mentioned)]
            random.shuffle(filtered)
            queries.extend(filtered[:2])

        if 'topic' in entities:
            pool_key = f"topic_{entities['topic']}"
            pool = self.query_pools.get(pool_key, [])
            filtered = [q for q in pool if not self._is_mentioned(q, mentioned)]
            random.shuffle(filtered)
            queries.extend(filtered[:2])

        if 'region' in entities:
            pool_key = f"region_{entities['region']}"
            pool = self.query_pools.get(pool_key, [])
            filtered = [q for q in pool if not self._is_mentioned(q, mentioned)]
            random.shuffle(filtered)
            queries.extend(filtered[:2])

        if 'type' in entities:
            pool_key = f"type_{entities['type']}"
            pool = self.query_pools.get(pool_key, [])
            filtered = [q for q in pool if not self._is_mentioned(q, mentioned)]
            random.shuffle(filtered)
            queries.extend(filtered[:2])

        return queries

    def _extract_entities(self, prompt: str) -> Dict[str, str]:
        entities = {}
        prompt_lower = prompt.lower()

        for industry, keywords in self.industries.items():
            if any(kw in prompt_lower for kw in keywords):
                entities['industry'] = industry
                break

        for region, keywords in self.regions.items():
            if any(kw in prompt_lower for kw in keywords):
                entities['region'] = region
                break

        for doc_type, keywords in self.doc_types.items():
            if any(kw in prompt_lower for kw in keywords):
                entities['type'] = doc_type
                break

        for topic, keywords in self.topics.items():
            if any(kw in prompt_lower for kw in keywords):
                entities['topic'] = topic
                break

        return entities

    def _expand_by_entities(self, entities: Dict, prompt: str, mentioned: set) -> List[str]:
        queries = []

        if 'industry' in entities:
            industry = entities['industry']
            related = self.relationships.get('industry', {}).get(industry, [])
            if related:
                related = related.copy()
                random.shuffle(related)
                for rel in related[:2]:
                    q = f"Add examples used by {rel}."
                    if not self._is_mentioned(q, mentioned):
                        queries.append(q)
                        break

        if 'topic' in entities:
            topic = entities['topic']
            related = self.relationships.get('topic', {}).get(topic, [])
            if related:
                related = related.copy()
                random.shuffle(related)
                for rel in related:
                    q = f"Include documentation for {rel}."
                    if not self._is_mentioned(q, mentioned):
                        queries.append(q)
                        break

        if 'region' in entities:
            region = entities['region']
            related = self.relationships.get('region', {}).get(region, [])
            if related:
                related = related.copy()
                random.shuffle(related)
                for rel in related:
                    q = f"Compare with {rel} standards."
                    if not self._is_mentioned(q, mentioned):
                        queries.append(q)
                        break

        return queries

    def _context_enhancements(self, prompt: str, entities: Dict, mentioned: set) -> List[str]:
        queries = []
        prompt_lower = prompt.lower()

        if not any(kw in prompt_lower for kw in ['recent', 'latest', 'updated', 'new', '2024', '2025']):
            opts = self.temporal_options.copy()
            random.shuffle(opts)
            queries.append(opts[0])

        if 'example' not in prompt_lower and 'case' not in prompt_lower:
            filtered = [q for q in self.practical_options if not self._is_mentioned(q, mentioned)]
            if filtered:
                random.shuffle(filtered)
                queries.append(filtered[0])

        filtered = [q for q in self.xref_options if not self._is_mentioned(q, mentioned)]
        if filtered:
            random.shuffle(filtered)
            queries.append(filtered[0])

        return queries

    def _is_valid(self, query: str, original: str) -> bool:
        if len(query) < 20 or len(query) > 80:
            return False

        meta = ['follow-up', 'suggestion', 'query', 'search', 'refinement']
        if any(m in query.lower() for m in meta):
            return False

        if self._similarity(query, original) > 0.5:
            return False

        return True

    def _similarity(self, a: str, b: str) -> float:
        stopwords = {'the', 'a', 'an', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'of', 'by'}
        words_a = set(a.lower().split()) - stopwords
        words_b = set(b.lower().split()) - stopwords
        if not words_a or not words_b:
            return 0
        return len(words_a & words_b) / len(words_a | words_b)

    def _rank_queries(self, queries: List[str], prompt: str, entities: Dict) -> List[Tuple[str, float]]:
        scored = []
        for q in queries:
            relevance = sum(1 for e in entities.values() if e.lower() in q.lower()) / max(len(entities), 1)

            specific_terms = ['iso', 'nist', 'pdf', 'editable', 'step-by-step', 'example', 'recent']
            specificity = sum(0.15 for t in specific_terms if t in q.lower())
            specificity = min(specificity + 0.4, 1.0)

            novelty = 1 - self._similarity(q, prompt)

            score = (relevance * 0.3) + (specificity * 0.4) + (novelty * 0.3)
            scored.append((q, score))

        return sorted(scored, key=lambda x: -x[1])

    def _select_diverse(self, ranked: List[Tuple[str, float]], max_k: int) -> List[str]:
        if len(ranked) <= max_k:
            return [q for q, _ in ranked]

        selected = [ranked[0]]
        remaining = ranked[1:]

        while len(selected) < max_k and remaining:
            best_mmr = -1
            best_idx = 0

            for i, (query, score) in enumerate(remaining):
                max_sim = max(self._similarity(query, s[0]) for s in selected)
                mmr = 0.7 * score - 0.3 * max_sim
                if mmr > best_mmr:
                    best_mmr = mmr
                    best_idx = i

            selected.append(remaining.pop(best_idx))

        return [q for q, _ in selected]
