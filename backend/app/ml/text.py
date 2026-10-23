"""Text normalisation shared by training and serving. Both sides import this
one function, so the features a model was trained on are exactly the features
it sees in production (no train/serve skew).

Light stemming and synonym folding let a bag-of-words model generalise across
phrasings ("signed", "signature", "countersigned" -> "sign")."""

import re

_DIGITS = re.compile(r"\d")
_NON_WORD = re.compile(r"[^a-z0-9 ]+")
_SPACES = re.compile(r"\s+")

_SYNONYMS = {
    "signature": "sign",
    "countersigned": "sign",
    "signed": "sign",
    "signing": "sign",
    "parcel": "package",
    "shipment": "package",
    "consignment": "package",
    "goods": "item",
    "merchandise": "item",
    "product": "item",
    "unit": "item",
    "courier": "carrier",
    "waybill": "receipt",
    "cardholder": "customer",
    "consignee": "recipient",
    "refunded": "refund",
    "credited": "credit",
    "reversed": "reversal",
    "authorization": "authorisation",
    "authorized": "authorisation",
    "authorised": "authorisation",
    "approved": "approval",
    "travelled": "travel",
    "traveled": "travel",
    "traveller": "travel",
    "flew": "fly",
    "flown": "fly",
    "boarded": "board",
    "boarding": "board",
    "downloaded": "download",
    "emailed": "email",
    "mailed": "email",
    "colour": "color",
    "offered": "offer",
    "accepted": "accept",
    "replace": "replacement",
}
_SUFFIXES = ("ations", "ation", "ments", "ment", "ings", "ing", "ed", "es", "s")


def _stem(word: str) -> str:
    word = _SYNONYMS.get(word, word)
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def normalize(text: str) -> str:
    text = _NON_WORD.sub(" ", _DIGITS.sub("0", text.lower()))
    return " ".join(_stem(word) for word in _SPACES.split(text) if word)


def candidate_spans(lines: list[str], window: int = 2) -> list[str]:
    """Evidence statements can wrap across OCR lines, so classify each line
    and each run of up to `window` consecutive lines."""
    spans = []
    for i in range(len(lines)):
        for size in range(1, window + 1):
            if i + size <= len(lines):
                spans.append(" ".join(lines[i : i + size]))
    return spans
