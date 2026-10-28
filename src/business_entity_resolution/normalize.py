"""Normalization primitives (Plan §6.1 v0).

`v0` is deliberately the minimum viable pass: case-fold + diacritic strip + tokenize,
drop the placeholders the data actually uses (`null`, `--`, empty), and optionally drop
the five legal suffixes explicitly given in the problem statement (DECISIONS.md D-05
compliance note — nothing else here is hand-authored; the mined tables land in NB03).

Kept Devanagari-aware (`\\u0900-\\u097f`) so transliteration cases survive the token
regex; a token like `टेक` normalizes to itself, not to nothing.
"""
from __future__ import annotations

import re
import unicodedata


# Placeholder tokens the raw data actually contains — observed in true pairs (§A.7).
_NULL_TOKENS: frozenset[str] = frozenset(
    {"null", "none", "na", "nan", "n/a", "--", ""}
)

# Only the five suffix pairs given verbatim in the problem statement. Mined suffix set
# lives in NB03 / normalization v1.
_ORGANIZER_GIVEN_SUFFIXES: frozenset[str] = frozenset(
    {"corp", "corporation", "pvt", "private", "ltd", "limited"}
)

# The organizer also explicitly lists punctuation variation ``&`` versus the word
# ``and`` in a business name.  ``&`` is removed by tokenization, so drop only this
# connector token to put the two supplied forms on the same normalized key.
_ORGANIZER_GIVEN_NAME_CONNECTOR_TOKENS: frozenset[str] = frozenset({"and"})

# Address abbreviations stated explicitly in the challenge's variation examples.
# This deliberately remains a tiny, transparent map: ambiguous abbreviations (for
# example ``dr``) and all learned transformations belong in later, validated stages.
_ORGANIZER_GIVEN_ADDRESS_ALIASES: dict[str, str] = {
    "rd": "road",
    "st": "street",
}

_TOKEN_RE = re.compile(r"[a-z0-9ऀ-ॿ]+")


def strip_diacritics(s: str) -> str:
    """Fold Latin accents while retaining marks used by non-Latin scripts.

    ``NFKD`` turns ``Café`` into ``Cafe`` plus a combining acute accent, which we
    want to discard.  It also exposes marks used by Devanagari (for example the
    virama and nukta).  Discarding *every* combining mark therefore altered Hindi
    tokens even though the tokenizer was advertised as Devanagari-aware.  A mark is
    removed only when its preceding base character is Latin.
    """
    if not s:
        return ""

    out: list[str] = []
    previous_base_is_latin = False
    for char in unicodedata.normalize("NFKD", s):
        # The corpus is predominantly ASCII.  Avoid an expensive Unicode-name
        # lookup for every ASCII byte during the multi-million-row S3 pass.
        if char.isascii():
            out.append(char)
            previous_base_is_latin = char.isalpha()
            continue
        if unicodedata.combining(char):
            if previous_base_is_latin:
                continue
            out.append(char)
            continue

        out.append(char)
        previous_base_is_latin = "LATIN" in unicodedata.name(char, "")
    return "".join(out)


def tokenize(s: str | None) -> list[str]:
    """Lowercase, strip diacritics, extract alphanumeric-or-Devanagari tokens, drop nulls."""
    if not s:
        return []
    s = strip_diacritics(s.lower())
    return [t for t in _TOKEN_RE.findall(s) if t not in _NULL_TOKENS]


def name_key(name: str | None, *, drop_suffix: bool = True) -> tuple[str, ...]:
    """Order-invariant name signature. Tuple so it's hashable."""
    toks = tokenize(name)
    if drop_suffix:
        toks = [
            t
            for t in toks
            if t not in _ORGANIZER_GIVEN_SUFFIXES
            and t not in _ORGANIZER_GIVEN_NAME_CONNECTOR_TOKENS
        ]
    return tuple(sorted(toks))


def address_key(addr: str | None) -> tuple[str, ...]:
    """Order-invariant address signature with documented abbreviation expansion."""
    return tuple(
        sorted(_ORGANIZER_GIVEN_ADDRESS_ALIASES.get(token, token) for token in tokenize(addr))
    )


def joint_key(
    name: str | None, addr: str | None, *, drop_suffix: bool = True
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(name_key, address_key). Convenience so callers only walk the strings once."""
    return name_key(name, drop_suffix=drop_suffix), address_key(addr)
