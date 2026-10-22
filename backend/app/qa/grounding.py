"""Deterministic, sentence-level grounding validation for model answers.

An answer is accepted only if every factual sentence cites at least one
provided passage and passes conservative checks against the passages it cites:

1. Citation policy: every bracketed token must be a well-formed label such as
   [P1] that was provided for this response, and a sentence may not repeat a
   label. Anything else rejects the whole answer.
2. Coverage: each factual sentence needs its own valid citation. A citation in
   another sentence does not count.
3. Quantities: every number in a sentence (number words such as "six" are
   normalised to digits) must appear in the sentence's cited passages, with the
   same unit when the sentence gives one.
4. Lexical support: at least half of the sentence's content words must appear
   in its cited passages.
5. Instruction-like text: passage sentences that read as instructions to an AI
   system (an override verb together with AI-control vocabulary, or two such
   terms) are not evidence. A sentence that is itself instruction-like, or that
   mostly repeats such passage text, is rejected.

These checks are lexical. They can show that an answer's words and quantities
come from the cited passages; they cannot show that the passage means what the
answer says. They are a filter, not proof of semantic grounding.
"""

import re
from dataclasses import dataclass

from app.qa.prompt import passage_label
from app.rag.store import RetrievedPassage

SUPPORT_THRESHOLD = 0.5  # fraction of content words found in cited evidence
INSTRUCTION_OVERLAP_THRESHOLD = 0.5  # fraction drawn from instruction-like text

_BRACKET = re.compile(r"\[[^\[\]]*\]")
_VALID_LABEL = re.compile(r"^P[1-9]\d*$")
_WORD = re.compile(r"[a-z0-9]+(?:[.,]\d+)*")
_NUMBER = re.compile(r"^\d+(?:[.,]\d+)*$")
_QUANTITY = re.compile(r"(\d+(?:[.,]\d+)*)\s*(%|[a-z]+)?")
_LEADING_CITATIONS = re.compile(r"^((?:\[[^\[\]]*\]\s*)+)")
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")

ABBREVIATIONS = frozenset(
    {
        "approx", "ca", "cf", "dept", "dr", "e.g", "eg", "est", "etc", "fig", "i.e",
        "ie", "incl", "max", "min", "mr", "mrs", "ms", "no", "nos", "st", "vs",
    }
)  # fmt: skip

NUMBER_WORDS = {
    word: str(value)
    for value, word in enumerate(
        [
            "zero",
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "nine",
            "ten",
            "eleven",
            "twelve",
            "thirteen",
            "fourteen",
            "fifteen",
            "sixteen",
            "seventeen",
            "eighteen",
            "nineteen",
            "twenty",
        ]
    )
}
NUMBER_WORDS.update(
    {
        "thirty": "30",
        "forty": "40",
        "fifty": "50",
        "sixty": "60",
        "seventy": "70",
        "eighty": "80",
        "ninety": "90",
        "hundred": "100",
    }
)

UNITS = {
    "%": "percent", "percent": "percent", "per": None,
    "l": "litre", "litre": "litre", "litres": "litre", "liter": "litre",
    "liters": "litre", "ml": "millilitre", "kg": "kilogram", "kilogram": "kilogram",
    "kilograms": "kilogram", "g": "gram", "gram": "gram", "grams": "gram",
    "km": "kilometre", "kilometre": "kilometre", "kilometres": "kilometre",
    "m": "metre", "metre": "metre", "metres": "metre", "meter": "metre",
    "meters": "metre", "hour": "hour", "hours": "hour", "hr": "hour", "hrs": "hour",
    "h": "hour", "minute": "minute", "minutes": "minute", "min": "minute",
    "mins": "minute", "day": "day", "days": "day", "week": "week", "weeks": "week",
    "month": "month", "months": "month", "person": "person", "persons": "person",
    "people": "person", "kit": "kit", "kits": "kit", "meal": "meal",
    "meals": "meal", "bed": "bed", "beds": "bed", "vehicle": "vehicle",
    "vehicles": "vehicle", "family": "family", "families": "family",
}  # fmt: skip

STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "by",
        "can",
        "could",
        "do",
        "does",
        "each",
        "every",
        "for",
        "from",
        "has",
        "have",
        "how",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "may",
        "might",
        "must",
        "of",
        "on",
        "or",
        "should",
        "so",
        "such",
        "than",
        "that",
        "the",
        "their",
        "them",
        "there",
        "these",
        "they",
        "this",
        "those",
        "to",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "will",
        "with",
        "would",
        "you",
        "your",
    ]
)

# Verbs that try to change an AI system's behaviour, and vocabulary about AI
# systems themselves. Ordinary disaster guidance rarely combines them.
OVERRIDE_TERMS = frozenset(
    [
        "ignore",
        "disregard",
        "forget",
        "override",
        "bypass",
        "reveal",
        "disclose",
        "print",
        "output",
        "pretend",
        "authorize",
        "authorise",
        "grant",
        "obey",
    ]
)
CONTROL_TERMS = frozenset(
    [
        "instruction",
        "instructions",
        "prompt",
        "prompts",
        "assistant",
        "chatbot",
        "ai",
        "llm",
        "jailbreak",
        "api",
        "secret",
        "secrets",
        "password",
        "passwords",
        "credential",
        "credentials",
        "token",
        "tokens",
        "tool",
        "tools",
        "validator",
        "validation",
    ]
)

_UNCERTAINTY = re.compile(
    r"^(?:the\s+)?(?:retrieved\s+|provided\s+)?(?:passages?|sources?|evidence|"
    r"documents?|guidance)\s+(?:do|does)\s+not\b"
    r"|^there\s+is\s+no\s+(?:information|evidence|guidance)\b"
    r"|^no\s+(?:information|evidence|guidance)\s+(?:is|was)\s+(?:given|provided|"
    r"available)\b"
    r"|^(?:i|we)\s+(?:could|can)\s*not\s+find\b"
    r"|^it\s+is\s+(?:not\s+clear|unclear)\b",
    re.IGNORECASE,
)
_CONTRAST = frozenset({"but", "however", "although", "though", "yet", "except"})

# Rule identifiers, in the order they are checked.
RULES = (
    "malformed_citation",
    "duplicate_citation",
    "unknown_label",
    "uncited_sentence",
    "suspicious_instruction",
    "number_not_in_cited_evidence",
    "low_lexical_support",
    "no_factual_sentence",
)


@dataclass(frozen=True)
class SentenceCheck:
    index: int
    factual: bool
    labels: tuple[str, ...]
    rule: str | None = None
    support: float | None = None


@dataclass(frozen=True)
class GroundingCheck:
    passed: bool
    rule: str | None
    sentences: tuple[SentenceCheck, ...]
    cited_labels: tuple[str, ...]

    @property
    def failed_sentence(self) -> int | None:
        return next((s.index for s in self.sentences if s.rule), None)


# Sentence segmentation ------------------------------------------------------------


def split_sentences(text: str) -> list[str]:
    """Conservatively split text into sentences.

    Lines are split first (lists are common). Within a line, a sentence ends at
    '.', '!' or '?' followed by whitespace, unless the period ends a known
    abbreviation or a single-letter initial, or the next word starts in lower
    case. Decimals such as 2.5 never split because no space follows the period.
    Citations written after the full stop ("... day. [P1]") stay with their
    sentence.
    """
    sentences: list[str] = []
    for line in text.splitlines():
        line = _BULLET.sub("", line).strip()
        if not line:
            continue
        start = 0
        for match in re.finditer(r"[.!?]+[\"')\]]*\s+", line):
            end = match.end()
            if line[match.start()] == "." and _is_abbreviation(line[: match.start()]):
                continue
            following = line[end:]
            if following[:1].islower():
                continue
            sentences.append(line[start:end].strip())
            start = end
        sentences.append(line[start:].strip())
    merged: list[str] = []
    for sentence in filter(None, sentences):
        leading = _LEADING_CITATIONS.match(sentence)
        if leading and merged:
            merged[-1] = f"{merged[-1]} {leading.group(1).strip()}"
            sentence = sentence[leading.end() :].strip()
        if sentence:
            merged.append(sentence)
    return merged


def _is_abbreviation(before: str) -> bool:
    token = re.search(r"([A-Za-z][A-Za-z.]*)$", before)
    if not token:
        return False
    word = token.group(1).lower()
    return word in ABBREVIATIONS or len(word) == 1


# Text normalisation ---------------------------------------------------------------


def _normalise_numbers(text: str) -> str:
    return re.sub(
        r"\b(" + "|".join(NUMBER_WORDS) + r")\b",
        lambda m: NUMBER_WORDS[m.group(1)],
        text.lower(),
    )


def _stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def content_words(text: str) -> set[str]:
    words = _WORD.findall(_normalise_numbers(_BRACKET.sub(" ", text)))
    return {_stem(w) for w in words if w not in STOPWORDS and not _NUMBER.match(w)}


def quantities(text: str) -> set[tuple[str, str | None]]:
    """(number, unit) pairs, with number words as digits and units normalised.
    The unit is None when the following word is not a known unit."""
    found = set()
    for number, unit in _QUANTITY.findall(_normalise_numbers(_BRACKET.sub(" ", text))):
        found.add((number.replace(",", ""), UNITS.get(unit) if unit else None))
    return found


def is_instruction_like(text: str) -> bool:
    words = set(_WORD.findall(text.lower()))
    control = len(words & CONTROL_TERMS)
    return control >= 2 or (control >= 1 and bool(words & OVERRIDE_TERMS))


def is_uncertainty_statement(sentence: str) -> bool:
    """An explicit statement about missing evidence, which makes no factual
    claim. It must not contain numbers or a contrast that could carry one."""
    text = _BRACKET.sub(" ", sentence).strip()
    words = set(_WORD.findall(text.lower()))
    return (
        bool(_UNCERTAINTY.match(text))
        and not words & _CONTRAST
        and not any(_NUMBER.match(w) for w in words)
    )


# Validation -----------------------------------------------------------------------


def check_grounding(text: str, passages: list[RetrievedPassage]) -> GroundingCheck:
    """Check an answer against the passages provided to the model, labelled P1,
    P2, ... in order. Returns the first failing rule, or passed=True."""
    by_label = {passage_label(i): p for i, p in enumerate(passages)}
    evidence = {label: _split_evidence(p.text) for label, p in by_label.items()}
    checks: list[SentenceCheck] = []
    cited: list[str] = []

    for index, sentence in enumerate(split_sentences(text), 1):
        tokens = [token[1:-1].strip() for token in _BRACKET.findall(sentence)]
        labels = tuple(t for t in tokens if _VALID_LABEL.match(t))
        rule = None
        if len(labels) != len(tokens):
            rule = "malformed_citation"
        elif len(set(labels)) != len(labels):
            rule = "duplicate_citation"
        elif any(label not in by_label for label in labels):
            rule = "unknown_label"
        words = content_words(sentence)
        factual = bool(words) and not is_uncertainty_statement(sentence)
        support = None
        if rule is None and factual:
            rule, support = _check_claim(sentence, words, labels, evidence)
        if rule is None and factual:
            cited.extend(label for label in labels if label not in cited)
        checks.append(SentenceCheck(index, factual, labels, rule, support))

    failed = next((c.rule for c in checks if c.rule), None)
    if failed is None and not any(c.factual for c in checks):
        failed = "no_factual_sentence"
    return GroundingCheck(
        passed=failed is None,
        rule=failed,
        sentences=tuple(checks),
        cited_labels=tuple(cited) if failed is None else (),
    )


def _split_evidence(passage_text: str) -> tuple[str, str]:
    """(usable evidence, instruction-like text) for one passage."""
    clean, suspicious = [], []
    for sentence in split_sentences(passage_text):
        (suspicious if is_instruction_like(sentence) else clean).append(sentence)
    return " ".join(clean), " ".join(suspicious)


def _check_claim(sentence, words, labels, evidence) -> tuple[str | None, float | None]:
    if not labels:
        return "uncited_sentence", None
    clean = " ".join(evidence[label][0] for label in labels)
    suspicious = " ".join(evidence[label][1] for label in labels)

    if is_instruction_like(sentence):
        return "suspicious_instruction", None
    if suspicious and words:
        drawn = len(words & content_words(suspicious)) / len(words)
        if drawn >= INSTRUCTION_OVERLAP_THRESHOLD:
            return "suspicious_instruction", None

    available = quantities(clean)
    available_numbers = {number for number, _ in available}
    for number, unit in quantities(sentence):
        if number not in available_numbers or (
            unit is not None and (number, unit) not in available
        ):
            return "number_not_in_cited_evidence", None

    if not words:  # only quantities, all of which matched
        return None, 1.0
    support = round(len(words & content_words(clean)) / len(words), 4)
    if support < SUPPORT_THRESHOLD:
        return "low_lexical_support", support
    return None, support
