"""Static AI-generation text heuristic detector using 5 statistical & stylistic signals.

Pure Python, no network calls or external APIs required.
"""
from __future__ import annotations
import math
import re
from typing import Tuple

STOCK_PHRASES = [
    "delve", "delving", "it is important to note", "in today's fast-paced",
    "comprehensive guide", "navigate the landscape", "unlock", "unlocking",
    "tapestry", "in conclusion", "furthermore", "moreover", "as an ai",
    "it is crucial to", "at the end of the day", "pivotal role",
    "testament to", "beacon of", "vital role", "rich tapestry",
    "look no further", "navigating the", "unlock the full potential",
    "stays informed", "cornerstone of success", "a wonderful opportunity",
    "in summary", "to summarize", "worth noting", "serves as a",
]

ASSISTANT_ARTIFACT_PATTERNS = [
    r"\bif you (need|would like|want) this (text|content|information|summary|article|response) (adapted|customized|tailored|formatted)",
    r"\blet me know (if you need|your target audience|how you would like|what tone|if you would like)",
    r"\bas an ai (language model|assistant)",
    r"\bi don't have personal opinions, but",
    r"\bi hope this (helps|summary helps|overview helps)",
    r"\bfeel free to ask if you have any (more|other) questions",
]

TRANSITION_STARTS = [
    "furthermore", "moreover", "additionally", "in addition", "in conclusion",
    "consequently", "therefore", "as a result", "importantly", "notably",
]

DIGIT_OR_DATE_RE = re.compile(r"\b(\d{1,4}|january|february|march|april|may|june|july|august|september|october|november|december|rs|₹)\b", re.IGNORECASE)


def detect_ai_generated(text: str) -> Tuple[float, bool]:
    """
    Returns (ai_probability_score: float in [0, 1], reliable: bool).
    If len(text) < 300 chars, returns (0.0, False).
    """
    if len(text) < 300:
        return 0.0, False

    words = re.findall(r"\b[a-zA-Z0-9'’-]+\b", text.lower())
    if len(words) < 30:
        return 0.0, False

    # 1. Stock-phrase density (weight 0.30)
    # Target: 0 hits -> 0.0, >= 8 hits per 1000 words -> 1.0
    text_lower = text.lower()
    total_words = len(words)
    stock_hits = sum(text_lower.count(phrase) for phrase in STOCK_PHRASES)
    hits_per_1000 = (stock_hits / total_words) * 1000.0
    stock_signal = min(1.0, hits_per_1000 / 7.0)

    # 2. Low burstiness (weight 0.25)
    # Low CV of sentence length means monotonous, uniform AI-like flow.
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if len(s.strip()) > 5]
    if len(sentences) >= 3:
        lengths = [len(re.findall(r"\b\w+\b", s)) for s in sentences]
        mean_len = sum(lengths) / len(lengths)
        if mean_len > 0:
            variance = sum((l - mean_len) ** 2 for l in lengths) / len(lengths)
            std_dev = math.sqrt(variance)
            cv = std_dev / mean_len
            # Natural human writing has high CV (often 0.6 - 1.2+).
            # Uniform AI text often has low CV (0.15 - 0.40).
            # Lower CV -> higher AI signal
            burstiness_signal = max(0.0, min(1.0, 1.0 - (cv / 0.75)))
        else:
            burstiness_signal = 0.5
    else:
        burstiness_signal = 0.5

    # 3. Lexical repetitiveness / Type-Token Ratio (weight 0.20)
    # Window of up to 300 words
    sample_window = words[:min(300, len(words))]
    unique_tokens = len(set(sample_window))
    ttr = unique_tokens / len(sample_window) if sample_window else 1.0
    # Trigram repetition rate
    trigrams = [tuple(sample_window[i:i+3]) for i in range(len(sample_window) - 2)]
    trigram_ratio = len(set(trigrams)) / len(trigrams) if trigrams else 1.0
    # Lower TTR + lower trigram diversity -> higher repetitiveness signal
    # Typical TTR on 300 words: 0.6-0.75 is normal, < 0.5 is repetitive
    ttr_signal = max(0.0, min(1.0, (0.75 - ttr) / 0.35))
    trigram_signal = max(0.0, min(1.0, (0.95 - trigram_ratio) / 0.15))
    lexical_signal = 0.6 * ttr_signal + 0.4 * trigram_signal

    # 4. Template structure (weight 0.15)
    # Lines with bullets, numbered lists, and paragraphs starting with transition words
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if lines:
        bullet_lines = sum(1 for line in lines if re.match(r"^(\d+[\.\)]|[-*•]|\([a-z0-9]+\))\s+", line, re.IGNORECASE))
        bullet_ratio = bullet_lines / len(lines)

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        transition_starts = sum(
            1 for p in paragraphs if any(p.lower().startswith(t) for t in TRANSITION_STARTS)
        )
        transition_ratio = transition_starts / len(paragraphs) if paragraphs else 0.0
        template_signal = min(1.0, (bullet_ratio * 0.8 + transition_ratio * 1.5))
    else:
        template_signal = 0.0

    # 5. Hedge / empty-claim ratio (weight 0.10)
    # Sentences with no digits, dates, currency, or concrete figures
    if sentences:
        empty_sentences = sum(1 for s in sentences if not DIGIT_OR_DATE_RE.search(s))
        hedge_ratio = empty_sentences / len(sentences)
        hedge_signal = max(0.0, min(1.0, (hedge_ratio - 0.2) / 0.6))
    else:
        hedge_signal = 0.0

    # Weighted combination
    composite_score = (
        0.30 * stock_signal +
        0.25 * burstiness_signal +
        0.20 * lexical_signal +
        0.15 * template_signal +
        0.10 * hedge_signal
    )

    # 6. Smoking-gun conversational assistant artifact override
    if any(re.search(pat, text_lower) for pat in ASSISTANT_ARTIFACT_PATTERNS):
        composite_score = max(composite_score, 0.95)

    final_score = round(max(0.0, min(1.0, composite_score)), 3)
    return final_score, True


from pydantic import BaseModel, ConfigDict, Field


class GeminiAIDetectOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ai_probability: float = Field(description="Probability between 0.0 and 1.0 that this text was generated by AI")
    is_ai_generated: bool
    reasoning: str


async def detect_ai_generated_gemini(text: str) -> Tuple[float, bool, str]:
    """
    Uses Gemini LLM to classify AI-generated likelihood and provide forensic reasoning.
    Falls back to statistical detector if LLM fails or is disabled.
    """
    if len(text) < 300:
        return 0.0, False, "Text too short (<300 chars)"

    from app.config import settings
    if settings.mock_mode or settings.mock_llm or not settings.llm_api_key:
        stat_score, rel = detect_ai_generated(text)
        return stat_score, rel, "Evaluated via statistical heuristic (offline/mock mode)"

    try:
        from app.llm import get_llm_client
        client = get_llm_client()
        system_prompt = (
            "You are an expert AI-generated content forensics classifier. "
            "Analyze the text for indicators of AI generation, including conversational assistant artifacts, "
            "synthetic bulleting, chatbot formatting, and generic style. "
            "Return JSON matching the schema."
        )
        sample = text[:3000]
        user_prompt = f"Analyze whether this text was generated by an AI assistant:\n\n{sample}"

        result = await client.generate_json(
            system=system_prompt,
            user=user_prompt,
            model_cls=GeminiAIDetectOutput,
            purpose="ai_detection",
        )
        return round(max(0.0, min(1.0, result.ai_probability)), 3), True, result.reasoning
    except Exception as e:
        stat_score, rel = detect_ai_generated(text)
        return stat_score, rel, f"Statistical fallback (LLM error: {e})"


