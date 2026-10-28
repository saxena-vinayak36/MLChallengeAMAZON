"""Memory-bounded normalization tables mined from labelled training pairs.

This module deliberately contains no external vocabulary.  It learns token
substitutions and dropped tokens from the supplied training ground truth only.
The caller feeds positive pairs in batches, so the miner is suitable for the
8 GiB execution environment used by this project.
"""
from __future__ import annotations

import collections
import json
import pathlib
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from .normalize import tokenize


_BASE_NAME_DROPS = frozenset(
    {"corp", "corporation", "pvt", "private", "ltd", "limited"}
)


@dataclass
class _FieldStats:
    pair_count: int = 0
    left_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    right_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    substitutions: collections.Counter[tuple[str, str]] = field(
        default_factory=collections.Counter
    )
    fuzzy_substitutions: collections.Counter[tuple[str, str]] = field(
        default_factory=collections.Counter
    )
    drops: collections.Counter[str] = field(default_factory=collections.Counter)

    def update(
        self, left: str | None, right: str | None, *, enable_fuzzy: bool = False
    ) -> None:
        a = set(tokenize(left))
        b = set(tokenize(right))
        self.pair_count += 1
        self.left_counts.update(a)
        self.right_counts.update(b)

        only_left = a - b
        only_right = b - a
        # Record only one-to-one differences.  For a many-to-many difference,
        # blindly creating every cross product would create unsafe aliases.
        if len(only_left) == 1 and len(only_right) == 1:
            self.substitutions[(next(iter(only_left)), next(iter(only_right)))] += 1
        else:
            # Only count a token as dropped when the positive pair does not
            # contain a clean one-to-one replacement.  This keeps ``rd ↔ road``
            # as an alias instead of incorrectly dropping both tokens.
            for token in only_left:
                self.drops[token] += 1
            for token in only_right:
                self.drops[token] += 1

            # Mine bounded spelling/abbreviation variants only for unresolved
            # many-token differences.  A clean one-to-one pair is already in
            # ``substitutions``; recording it here too would double its support.
            if enable_fuzzy and 0 < len(only_left) <= 4 and 0 < len(only_right) <= 4:
                for a in only_left:
                    candidates = [
                        b for b in only_right
                        if abs(len(a) - len(b)) <= 2
                        and _edit_distance_at_most(a, b, limit=2) <= 2
                    ]
                    if len(candidates) == 1:
                        self.fuzzy_substitutions[(a, candidates[0])] += 1


def _edit_distance_at_most(a: str, b: str, *, limit: int) -> int:
    """Return edit distance, abandoning rows that already exceed ``limit``."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        row_min = i
        for j, cb in enumerate(b, 1):
            value = min(
                current[-1] + 1,
                previous[j] + 1,
                previous[j - 1] + (ca != cb),
            )
            current.append(value)
            row_min = min(row_min, value)
        if row_min > limit:
            return limit + 1
        previous = current
    return previous[-1]


@dataclass(frozen=True)
class MinedNormalization:
    """Serializable v1 tables used by later blocking/features stages."""

    name_aliases: Mapping[str, str]
    address_aliases: Mapping[str, str]
    name_drop_tokens: tuple[str, ...]
    address_drop_tokens: tuple[str, ...]
    name_support: Mapping[str, int]
    address_support: Mapping[str, int]
    config: Mapping[str, object]

    def normalize_tokens(
        self,
        value: str | None,
        *,
        field_name: str,
    ) -> tuple[str, ...]:
        aliases = self.name_aliases if field_name == "name" else self.address_aliases
        drops = set(
            self.name_drop_tokens if field_name == "name" else self.address_drop_tokens
        )
        out = {aliases.get(token, token) for token in tokenize(value)}
        if field_name == "name":
            out.difference_update(_BASE_NAME_DROPS)
        return tuple(sorted(token for token in out if token not in drops))

    def name_key(self, value: str | None) -> tuple[str, ...]:
        return self.normalize_tokens(value, field_name="name")

    def address_key(self, value: str | None) -> tuple[str, ...]:
        return self.normalize_tokens(value, field_name="address")

    def joint_key(
        self, name: str | None, address: str | None
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return self.name_key(name), self.address_key(address)

    def to_dict(self) -> dict[str, object]:
        return {
            "name_aliases": dict(self.name_aliases),
            "address_aliases": dict(self.address_aliases),
            "name_drop_tokens": list(self.name_drop_tokens),
            "address_drop_tokens": list(self.address_drop_tokens),
            "name_support": dict(self.name_support),
            "address_support": dict(self.address_support),
            "config": dict(self.config),
        }


def _select_aliases(
    stats: _FieldStats,
    *,
    min_support: int,
    min_confidence: float,
) -> tuple[dict[str, str], dict[str, int]]:
    """Select conservative one-to-one token aliases from pair statistics."""
    proposals: list[tuple[float, int, str, str]] = []
    all_substitutions = stats.substitutions.copy()
    all_substitutions.update(stats.fuzzy_substitutions)

    # The old denominator was the number of *all* positive pairs containing a
    # token.  That makes a valid alias such as ``rd -> road`` almost impossible
    # to select: most observations contain ``rd`` on both sides and are not
    # transformation opportunities.  Confidence must instead answer the useful
    # question: conditional on seeing this one-to-one token difference, how
    # consistently does it map to this counterpart?
    left_opportunities: collections.Counter[str] = collections.Counter()
    right_opportunities: collections.Counter[str] = collections.Counter()
    for (left, right), support in all_substitutions.items():
        left_opportunities[left] += support
        right_opportunities[right] += support

    for (left, right), support in all_substitutions.items():
        if support < min_support:
            continue
        confidence = min(
            support / max(1, left_opportunities[left]),
            support / max(1, right_opportunities[right]),
        )
        if confidence >= min_confidence:
            proposals.append((confidence, support, left, right))

    aliases: dict[str, str] = {}
    used_right: set[str] = set()
    support_out: dict[str, int] = {}
    for _, support, left, right in sorted(proposals, reverse=True):
        if left in aliases or right in used_right:
            continue
        aliases[left] = right
        used_right.add(right)
        support_out[left] = support
    return aliases, support_out


def _select_drops(
    stats: _FieldStats,
    *,
    min_support: int,
    min_drop_rate: float,
) -> tuple[str, ...]:
    """Select tokens that are consistently absent on one side of positives."""
    selected = []
    for token, count in stats.drops.items():
        if count < min_support:
            continue
        # A token is eligible only when it is dropped far more often than it
        # survives in the field.  This avoids turning ordinary business words
        # into globally removed stopwords.
        # ``drops`` counts positive pairs where the token occurs on one side
        # but not the other.  Its denominator is the number of appearances of
        # *that token*, not all 7M positive pairs.  The latter made every
        # realistic suffix/drop rate close to zero and therefore guaranteed an
        # empty table at the configured 0.80 threshold.
        present = stats.left_counts[token] + stats.right_counts[token]
        rate = count / max(1, present)
        if rate >= min_drop_rate:
            selected.append(token)
    return tuple(sorted(selected))


class NormalizationMiner:
    """Incrementally mine name/address transformations from positive pairs."""

    def __init__(self, *, enable_fuzzy: bool = False) -> None:
        """Create a miner.

        Fuzzy token comparisons are deliberately off for the S3 baseline.  Applying
        dynamic-programming edit distance to every unresolved positive pair turns a
        memory-bounded streaming pass into a multi-hour CPU job on the 2-vCPU EC2
        host.  Exact one-to-one substitutions still cover the safe mined-alias
        experiment; typo/transliteration recovery is a separate S3 variant.
        """
        self.name = _FieldStats()
        self.address = _FieldStats()
        self.enable_fuzzy = enable_fuzzy

    def update(self, pairs: Iterable[tuple[str, str, str, str]]) -> None:
        """Consume ``(name_left, name_right, address_left, address_right)`` rows."""
        for name_left, name_right, address_left, address_right in pairs:
            self.name.update(name_left, name_right, enable_fuzzy=self.enable_fuzzy)
            self.address.update(
                address_left, address_right, enable_fuzzy=self.enable_fuzzy
            )

    def stats_summary(self) -> dict[str, dict[str, int]]:
        """Return diagnostics explaining what the conservative gates saw.

        These counts make an empty alias table interpretable: either no
        candidate transformations existed, or they existed but failed a chosen
        support/confidence threshold.
        """

        def summarize(stats: _FieldStats) -> dict[str, int]:
            return {
                "positive_pairs": stats.pair_count,
                "exact_substitution_observations": sum(stats.substitutions.values()),
                "exact_substitution_types": len(stats.substitutions),
                "fuzzy_substitution_observations": sum(
                    stats.fuzzy_substitutions.values()
                ),
                "fuzzy_substitution_types": len(stats.fuzzy_substitutions),
                "drop_observations": sum(stats.drops.values()),
                "drop_token_types": len(stats.drops),
            }

        return {"name": summarize(self.name), "address": summarize(self.address)}

    def finish(
        self,
        *,
        min_support: int = 10,
        min_confidence: float = 0.90,
        min_drop_rate: float = 0.80,
        min_drop_support: int = 1000,
    ) -> MinedNormalization:
        name_aliases, name_support = _select_aliases(
            self.name,
            min_support=min_support,
            min_confidence=min_confidence,
        )
        address_aliases, address_support = _select_aliases(
            self.address,
            min_support=min_support,
            min_confidence=min_confidence,
        )
        return MinedNormalization(
            name_aliases=name_aliases,
            address_aliases=address_aliases,
            name_drop_tokens=_select_drops(
                self.name,
                min_support=min_drop_support,
                min_drop_rate=min_drop_rate,
            ),
            address_drop_tokens=_select_drops(
                self.address,
                min_support=min_drop_support,
                min_drop_rate=min_drop_rate,
            ),
            name_support=name_support,
            address_support=address_support,
            config={
                "min_support": min_support,
                "min_confidence": min_confidence,
                "min_drop_rate": min_drop_rate,
                "min_drop_support": min_drop_support,
                "enable_fuzzy": self.enable_fuzzy,
            },
        )


def save_mined_tables(tables: MinedNormalization, path: str | pathlib.Path) -> None:
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tables.to_dict(), indent=2, sort_keys=True) + "\n")


def load_mined_tables(path: str | pathlib.Path) -> MinedNormalization:
    payload = json.loads(pathlib.Path(path).read_text())
    return MinedNormalization(
        name_aliases=payload["name_aliases"],
        address_aliases=payload["address_aliases"],
        name_drop_tokens=tuple(payload["name_drop_tokens"]),
        address_drop_tokens=tuple(payload["address_drop_tokens"]),
        name_support=payload["name_support"],
        address_support=payload["address_support"],
        config=payload["config"],
    )
