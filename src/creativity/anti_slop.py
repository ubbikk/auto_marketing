"""Anti-slop validation for detecting and filtering AI-generated content patterns.

Based on research showing AI-identified posts receive 45% fewer engagements.
Implements detection for words/phrases/patterns that signal AI generation.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ValidationResult:
    """Result of anti-slop validation."""

    is_valid: bool
    score: float  # 0-10, higher is better (less slop)
    violations: list[str]
    warnings: list[str]


class AntiSlopValidator:
    """Detects and flags AI slop patterns in generated content."""

    # Words with 700-1500% increase post-ChatGPT (from academic research)
    BANNED_WORDS = {
        # Highest offenders (1000%+ increase)
        "delve",
        "tapestry",
        "testament",
        "realm",
        "underscore",
        "intricate",
        # High frequency AI words
        "leverage",
        "harness",
        "unlock",
        "embark",
        "robust",
        "seamless",
        "pivotal",
        "comprehensive",
        "furthermore",
        "moreover",
        "elevate",
        "foster",
        "landscape",
        "paradigm",
        "synergy",
        "navigate",
        "multifaceted",
        "nuanced",
        "dynamic",
        "holistic",
        "streamline",
        "optimize",
        "empower",
        "innovative",
        "cutting-edge",
        "game-changer",
        "revolutionary",
        "transformative",
        "impactful",
        "actionable",
        "proactive",
        "scalable",
        "ecosystem",
        "stakeholder",
        "bandwidth",
        "synergize",
        "incentivize",
        "operationalize",
    }

    BANNED_PHRASES = [
        # Classic AI openers
        "In today's fast-paced world",
        "In today's digital age",
        "In today's competitive landscape",
        "It's worth noting that",
        "It's important to note",
        "Let's dive in",
        "Let's explore",
        "Without further ado",
        "First and foremost",
        "Last but not least",
        "At the end of the day",
        # AI closers
        "In conclusion",
        "To sum up",
        "In summary",
        "Moving forward",
        # Engagement bait
        "What do you think?",
        "Drop a comment below",
        "Let me know in the comments",
        "Share your thoughts",
        "Agree or disagree?",
        # Empty intensifiers
        "Game-changer",
        "Take it to the next level",
        "Unlock your potential",
        "Level up",
        "Supercharge",
        # Corporate speak
        "Circle back",
        "Touch base",
        "Move the needle",
        "Low-hanging fruit",
        "Think outside the box",
        "Hit the ground running",
        "Best practices",
        "Value proposition",
        "Core competencies",
    ]

    # Regex patterns for structural AI tells
    BANNED_PATTERNS = [
        # Emoji spam openers
        (r"^[\U0001F300-\U0001F9FF\s]{2,}", "Emoji opener"),
        # Multiple emojis in a row
        (
            r"[\U0001F300-\U0001F9FF]{3,}",
            "Emoji spam",
        ),
        # ChatGPT em-dash overuse (more than 2 per post)
        (r"—[^—]+—.*—[^—]+—", "Em-dash overuse"),
        # Weak openers
        (r"(?i)^(so,?\s|here'?s the thing|let me tell you)", "Weak opener"),
        # Generic question endings
        (r"(?i)what do you think\s*\??$", "Engagement bait ending"),
        # Numbered lists in LinkedIn style
        (r"(?m)^[1-9]\.\s.*\n[1-9]\.\s.*\n[1-9]\.\s", "Listicle format"),
        # Excessive exclamation marks
        (r"!{2,}", "Multiple exclamation marks"),
        # AI rhetorical questions mid-text
        (r"(?i)\?\s+(The answer|It's simple|Here's why)", "Rhetorical question pattern"),
        # Snappy triads pattern
        (
            r"(?i)(clear,?\s+concise,?\s+and\s+compelling|fast,?\s+easy,?\s+and\s+effective)",
            "Snappy triad cliche",
        ),
    ]

    # Warning patterns (not violations but worth noting)
    WARNING_PATTERNS = [
        (r"(?i)here'?s (what|why|how)", "Generic intro pattern"),
        (r"(?i)the (truth|reality|fact) is", "Dramatic reveal pattern"),
        (r"(?i)imagine (if|this|a world)", "Imagine opener"),
    ]

    def __init__(self, custom_banned_path: Optional[Path] = None):
        """Initialize validator with optional custom banned words file."""
        self.banned_words = self.BANNED_WORDS.copy()
        self.banned_phrases = self.BANNED_PHRASES.copy()
        self.banned_patterns = [(re.compile(p), desc) for p, desc in self.BANNED_PATTERNS]
        self.warning_patterns = [(re.compile(p), desc) for p, desc in self.WARNING_PATTERNS]

        if custom_banned_path and custom_banned_path.exists():
            self._load_custom(custom_banned_path)

    def _load_custom(self, path: Path) -> None:
        """Load custom banned words from file."""
        with open(path) as f:
            for line in f:
                word = line.strip().lower()
                if word and not word.startswith("#"):
                    self.banned_words.add(word)

    def validate(self, text: str) -> ValidationResult:
        """
        Validate text against anti-slop rules.

        Returns ValidationResult with:
        - is_valid: True if no hard violations
        - score: 0-10 quality score (10 = no slop detected)
        - violations: List of rule violations
        - warnings: List of potential issues
        """
        violations = []
        warnings = []
        text_lower = text.lower()

        # Check banned words
        for word in self.banned_words:
            # Match whole words only
            pattern = rf"\b{re.escape(word)}\b"
            if re.search(pattern, text_lower):
                violations.append(f"Banned word: '{word}'")

        # Check banned phrases
        for phrase in self.banned_phrases:
            if phrase.lower() in text_lower:
                violations.append(f"Banned phrase: '{phrase}'")

        # Check banned patterns
        for pattern, description in self.banned_patterns:
            if pattern.search(text):
                violations.append(f"Banned pattern: {description}")

        # Check warning patterns
        for pattern, description in self.warning_patterns:
            if pattern.search(text):
                warnings.append(f"Warning: {description}")

        # Additional quality checks
        warnings.extend(self._check_quality_signals(text))

        # Calculate score
        score = self._calculate_score(violations, warnings, text)

        return ValidationResult(
            is_valid=len(violations) == 0,
            score=score,
            violations=violations,
            warnings=warnings,
        )

    def _check_quality_signals(self, text: str) -> list[str]:
        """Check for additional quality signals."""
        warnings = []

        # Check sentence length variation (burstiness)
        sentences = re.split(r"[.!?]+", text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if len(sentences) >= 3:
            lengths = [len(s.split()) for s in sentences]
            avg_len = sum(lengths) / len(lengths)
            variance = sum((l - avg_len) ** 2 for l in lengths) / len(lengths)
            if variance < 5:  # Low variance = monotonous
                warnings.append("Low sentence length variation (monotonous rhythm)")

        # Check for specific numbers (good sign if present)
        has_specific_number = bool(re.search(r"\b\d{2,}\b", text))
        if not has_specific_number and len(text) > 200:
            warnings.append("No specific numbers found (vagueness indicator)")

        # Check for overly long paragraphs
        paragraphs = text.split("\n\n")
        for para in paragraphs:
            if len(para.split()) > 100:
                warnings.append("Overly long paragraph (wall of text)")
                break

        return warnings

    def _calculate_score(self, violations: list, warnings: list, text: str) -> float:
        """Calculate quality score from 0-10."""
        score = 10.0

        # Major deductions for violations
        score -= len(violations) * 1.5

        # Minor deductions for warnings
        score -= len(warnings) * 0.3

        # Bonus for specific details
        if re.search(r"\$\d+", text):
            score += 0.5
        if re.search(r"\d+%", text):
            score += 0.3
        if re.search(r"\d+\s*(hours?|days?|weeks?)", text):
            score += 0.3

        return max(0.0, min(10.0, score))

    def get_rules_for_prompt(self) -> str:
        """Return anti-slop rules formatted for inclusion in prompts."""
        top_banned = sorted(list(self.banned_words))[:20]
        top_phrases = self.banned_phrases[:10]

        return f"""
ANTI-SLOP RULES (CRITICAL - VIOLATIONS WILL DISQUALIFY YOUR RESPONSE):

BANNED WORDS - NEVER use these:
{', '.join(top_banned)}

BANNED PHRASES - NEVER use these:
{chr(10).join(f'- "{p}"' for p in top_phrases)}

PATTERNS TO AVOID:
- Starting with emojis
- Em-dash overuse (the "ChatGPT dash") - max 1 per post
- Ending with "What do you think?" or similar engagement bait
- Numbered lists (1. 2. 3. format)
- Multiple exclamation marks!!
- Snappy triads ("clear, concise, and compelling")

QUALITY SIGNALS TO INCLUDE:
- Specific numbers ($47K, 73%, 2 hours)
- Sentence length variation (mix short punches with longer explanations)
- Concrete examples, not abstract claims
- Something surprising or contrarian

If you catch yourself writing ANY banned content, STOP and find a more original way.
"""

    def quick_check(self, text: str) -> bool:
        """Quick check for obvious violations without full analysis."""
        text_lower = text.lower()

        # Check top offenders only
        top_offenders = {"delve", "leverage", "unlock", "seamless", "robust"}
        for word in top_offenders:
            if re.search(rf"\b{word}\b", text_lower):
                return False

        # Check worst phrases
        worst_phrases = ["In today's", "Let's dive in", "What do you think?"]
        for phrase in worst_phrases:
            if phrase.lower() in text_lower:
                return False

        return True
