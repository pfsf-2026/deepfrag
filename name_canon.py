#!/usr/bin/env python3
"""Player-name canonicalization for QuakeWorld stats.

QW player names carry color codes via high-bit bytes (0xa0–0xfe) and may include
decorative brackets, numbers, and clan prefixes. The same human shows up under
many spellings: "Cronus", "cronus", "cr\\efnus" (yellow O), "[FK]cronus", etc.

This module produces a canonical_id (slug) for every raw in-game name, using:

  1. Hub `login` field  — authoritative. Same login = same person, full stop.
  2. Auto-normalize     — strip color codes (high-bit → ASCII), lowercase, trim
                          leading/trailing decorative chars.
  3. Fuzzy match        — Levenshtein-distance match against existing canonicals.
                          Borderline cases go to a review queue for manual approval.
  4. Manual aliases     — aliases.yaml overrides everything else.

Usage:
  from name_canon import Canonicalizer
  c = Canonicalizer.load()
  cid, decision = c.resolve("crïnus", login=None)
  # cid="cronus", decision="auto"|"manual"|"fuzzy"|"new"|"review"
"""

import argparse
import difflib
import json
import re
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


ALIASES_PATH = Path(__file__).parent / "aliases.yaml"
REVIEW_QUEUE_PATH = Path(__file__).parent / ".review_queue.yaml"

# Fuzzy thresholds. SequenceMatcher.ratio() returns 0.0–1.0.
#   AUTO_MERGE: collapse silently into existing canonical
#   REVIEW    : surface for human decision (between REVIEW and AUTO_MERGE)
#   Below REVIEW: treated as a brand-new canonical
AUTO_MERGE_RATIO = 0.92
REVIEW_RATIO    = 0.78

# Minimum length for fuzzy matching to apply at all.
# Short names (≤3 chars) generate too many false positives.
MIN_FUZZY_LEN = 4


def strip_color_codes(name: str) -> str:
    """Map QW high-bit colored chars back to their ASCII equivalents, drop control chars.

    Handles RAW QW byte form (what xantom's archives use). For the pre-escaped form
    that our own sync.py produces ('cr\\5onus'), apply unescape_qw_name() first.

    QW palette:
      0x20-0x7e → printable ASCII (kept as-is)
      0xa0-0xfe → ASCII + 128  (subtract 128 to recover letter/digit/symbol)
      0x10-0x1b, 0x90-0x9b → bracket-style decorations → drop
      0x00, 0x0a-0x0f → control → drop
    """
    out = []
    for ch in name:
        o = ord(ch)
        if 0x20 <= o <= 0x7e:
            out.append(ch)
        elif 0xa0 <= o <= 0xfe:
            # Special case: 0xa0 = colored space → space
            out.append(' ' if o == 0xa0 else chr(o - 128))
        elif 0x12 <= o <= 0x1b:
            # Yellow digits 0-9 in QW palette (see charset row 0x10)
            out.append(chr(o + 0x1e))
        elif 0x92 <= o <= 0x9b:
            # Gold-yellow digits 0-9 (charset row 0x90)
            out.append(chr(o - 0x62))
        # Everything else (color bracket chars, control bytes) is decoration — drop.
    return ''.join(out)


def unescape_qw_name(s: str) -> str:
    """Reverse the escape_qw() encoding produced by sync.py.

    sync.py converts raw QW bytes to a printable escape form for storage:
      0xef (yellow 'o') → '\\5o'    (color marker + the ASCII letter)
      0x10, 0x11        → '\\1[', '\\1]'
      0x12-0x1b         → '\\2X'    (drop the marker, drop the char)
      0x90, 0x91        → '\\3[', '\\3]'
      0x92-0x9b         → '\\4X'
      0xdc              → '\\5\\\\' (yellow backslash)
      other 0xa0-0xfe   → '\\5X'    (yellow colored char → ASCII X)
      0x5c              → '\\\\'    (literal backslash)
      other unknown     → '\\xNN'

    This function reverses that, recovering plain ASCII content. Brackets and
    pure decoration are dropped; letters/digits/symbols are kept.

    Examples:
      'cr\\5onus'           → 'cronus'   (the \\5 marker is dropped, 'o' kept)
      '\\5Bance'            → 'Bance'
      'BLooD_DoG(D_P)'      → 'BLooD_DoG(D_P)'  (no escapes)
    """
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c != '\\' or i + 1 >= n:
            out.append(c)
            i += 1
            continue
        nxt = s[i + 1]
        if nxt == '\\':                 # \\  → '\'
            out.append('\\')
            i += 2
        elif nxt == 'x' and i + 3 < n:  # \xNN → drop unknown byte
            i += 4
        elif nxt == '1':                # \1[ or \1] = brackets — drop
            if i + 2 < n and s[i + 2] in '[]':
                i += 3
            else:
                i += 2 if i + 2 >= n else 3
        elif nxt == '2':                # \2X where X='0'..'9' = yellow digit (byte 0x12+X) — KEEP X
            if i + 2 < n and s[i + 2].isdigit():
                out.append(s[i + 2])
                i += 3
            else:
                i += 3 if i + 2 < n else 2
        elif nxt == '3':                # \3[ or \3] = yellow brackets — drop
            if i + 2 < n and s[i + 2] in '[]':
                i += 3
            else:
                i += 2 if i + 2 >= n else 3
        elif nxt == '4':                # \4X where X='0'..'9' = gold-yellow digit (byte 0x92+X) — KEEP X
            if i + 2 < n and s[i + 2].isdigit():
                out.append(s[i + 2])
                i += 3
            else:
                i += 3 if i + 2 < n else 2
        elif nxt == '5':                # \5X → drop marker, keep X (it's the ASCII letter)
            if i + 3 < n and s[i + 2:i + 4] == '\\\\':
                out.append('\\')        # \5\\ → '\\' (yellow backslash)
                i += 4
            elif i + 2 < n:
                out.append(s[i + 2])
                i += 3
            else:
                i += 2
        else:                           # unknown escape — keep verbatim
            out.append(c)
            i += 1
    return ''.join(out)


# Characters considered "decorative" at the boundary of a name — trimmed off.
DECORATIVE_BOUNDARY = re.compile(r'^[\s\[\]\(\)\{\}<>|\\\/*+\-_=~`!@#$%^&.,;:?"\']+|[\s\[\]\(\)\{\}<>|\\\/*+\-_=~`!@#$%^&.,;:?"\']+$')


def clean_for_display(name: str) -> str:
    """Produce a human-readable display version of a raw name.

    Like normalize() but preserves case and inner punctuation — only strips QW
    escape sequences ('\\5o' → 'o') and raw high-bit color bytes (0xef → 'o').
    Used by canonicalize.py when picking the canonical's display_name.
    """
    s = unescape_qw_name(name)
    s = strip_color_codes(s)
    s = DECORATIVE_BOUNDARY.sub('', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


# Known regional/clan prefixes that players prepend to their names (especially
# in 4on4). When matched, strip the prefix so 'au.reload' folds into 'reload'.
# Conservative list — only strip if the prefix is in this set, so accidental
# matches like 'go.fish' (not a regional code) survive.
REGIONAL_PREFIXES = frozenset({
    'au', 'na', 'eu', 'sa',                   # continent codes
    'uk', 'us', 'ru', 'de', 'fr', 'se', 'fi', # country codes
    'no', 'dk', 'nl', 'it', 'es', 'br', 'jp',
    'kr', 'cn', 'pl', 'cz', 'hu', 'ie', 'be',
    'ca', 'mx', 'ar', 'cl', 'pt', 'gr', 'tr',
    'at', 'ch', 'il', 'au', 'nz', 'za',
})
REGIONAL_PREFIX_RE = re.compile(r'^([a-z]{2})\.(.+)$')


def normalize(name: str) -> str:
    """Canonicalize a name to its plain-lowercase form, regardless of how it was stored.

    Handles:
      - RAW QW bytes (e.g. 'cr<0xef>nus' from xantom archives)
      - PRE-ESCAPED form (e.g. 'cr\\5onus' from our existing sync.py)
      - Regional prefixes (e.g. 'au.reload' → 'reload')

    Examples:
      'Cronus'        → 'cronus'
      'cr\\5onus'     → 'cronus'   (escaped yellow 'o')
      'cr<0xef>nus'   → 'cronus'   (raw yellow 'o')
      'au.reload'     → 'reload'   (australian regional prefix stripped)
      '  cronus_  '   → 'cronus'
    """
    s = unescape_qw_name(name)
    s = strip_color_codes(s).lower()
    s = DECORATIVE_BOUNDARY.sub('', s)
    s = re.sub(r'\s+', ' ', s).strip()
    # Strip recognized regional prefix (e.g. 'au.reload' → 'reload')
    m = REGIONAL_PREFIX_RE.match(s)
    if m and m.group(1) in REGIONAL_PREFIXES:
        s = m.group(2).strip()
    return s


def fuzzy_ratio(a: str, b: str) -> float:
    """Similarity score 0.0–1.0 between two normalized names.

    Uses stdlib SequenceMatcher (Ratcliff/Obershelp) — fast enough for our scale.
    """
    return difflib.SequenceMatcher(None, a, b).ratio()


@dataclass
class CanonicalRecord:
    canonical_id: str
    display: str
    login: str = ""
    variants: set = field(default_factory=set)        # normalized names that resolve here
    excludes: set = field(default_factory=set)        # normalized names explicitly NOT this person


@dataclass
class ReviewEntry:
    raw_name: str
    normalized: str
    suggested_canonical: str
    score: float
    seen_count: int = 1
    decision: str = "pending"   # pending / accept / reject

    def to_yaml(self):
        return {
            "raw": self.raw_name,
            "normalized": self.normalized,
            "suggested_canonical": self.suggested_canonical,
            "score": round(self.score, 3),
            "seen_count": self.seen_count,
            "decision": self.decision,
        }


class Canonicalizer:
    def __init__(self, records: dict, review_queue: list = None):
        # canonical_id → CanonicalRecord
        self.records = records
        # raw_name → canonical_id cache (filled as we resolve)
        self.cache = {}
        # Index for quick lookup: normalized → canonical_id
        self.normalized_index = {}
        for cid, rec in records.items():
            for v in rec.variants:
                self.normalized_index[v] = cid
        # Login index
        self.login_index = {rec.login: cid for cid, rec in records.items() if rec.login}
        # Pending review queue (raw_name → ReviewEntry)
        self.review_queue = {e.raw_name: e for e in (review_queue or [])}

    @classmethod
    def load(cls, aliases_path=ALIASES_PATH, queue_path=REVIEW_QUEUE_PATH):
        records = {}
        if aliases_path.exists():
            data = yaml.safe_load(aliases_path.read_text()) or {}
            for cid, payload in data.items():
                payload = payload or {}
                rec = CanonicalRecord(
                    canonical_id=cid,
                    display=payload.get("display", cid),
                    login=payload.get("login", "") or "",
                    variants=set(v.lower() for v in payload.get("variants", [])),
                    excludes=set(v.lower() for v in payload.get("excludes", [])),
                )
                # Auto-include the canonical_id as a variant
                rec.variants.add(cid.lower())
                records[cid] = rec
        queue = []
        if queue_path.exists():
            data = yaml.safe_load(queue_path.read_text()) or []
            for d in data:
                queue.append(ReviewEntry(
                    raw_name=d["raw"], normalized=d["normalized"],
                    suggested_canonical=d["suggested_canonical"], score=d["score"],
                    seen_count=d.get("seen_count", 1), decision=d.get("decision", "pending"),
                ))
        return cls(records, queue)

    def save_review_queue(self, path=REVIEW_QUEUE_PATH):
        if not self.review_queue:
            if path.exists():
                path.unlink()
            return
        path.write_text(yaml.safe_dump(
            [e.to_yaml() for e in sorted(self.review_queue.values(), key=lambda x: (-x.seen_count, x.raw_name))],
            sort_keys=False,
        ))

    def save_aliases(self, path=ALIASES_PATH):
        """Persist current canonicals back to YAML (used after accepting reviews)."""
        out = {}
        for cid, rec in sorted(self.records.items()):
            out[cid] = {
                "display": rec.display,
                "login": rec.login,
                "variants": sorted(v for v in rec.variants if v != cid.lower()),
            }
            if rec.excludes:
                out[cid]["excludes"] = sorted(rec.excludes)
        path.write_text(yaml.safe_dump(out, sort_keys=False, allow_unicode=True))

    def resolve(self, raw_name: str, login: str = None) -> tuple:
        """Return (canonical_id, decision) where decision is one of:
        'login' | 'manual' | 'auto' | 'fuzzy' | 'new' | 'review'

        'review' means we couldn't decide — queued for manual approval. The
        returned canonical_id in that case is a tentative new slug.
        """
        if raw_name in self.cache:
            return self.cache[raw_name], "cached"

        norm = normalize(raw_name)
        if not norm:
            cid = "_unknown"
            self.cache[raw_name] = cid
            return cid, "empty"

        # 1. Login-based identity (highest priority)
        if login and login in self.login_index:
            cid = self.login_index[login]
            self._record_variant(cid, norm)
            self.cache[raw_name] = cid
            return cid, "login"

        # 2. Exact normalized match against existing canonical or its variants
        if norm in self.normalized_index:
            cid = self.normalized_index[norm]
            self.cache[raw_name] = cid
            return cid, "manual" if norm in self.records[cid].variants else "auto"

        # 3. Fuzzy match (Levenshtein-style ratio)
        if len(norm) >= MIN_FUZZY_LEN:
            best_cid = None
            best_score = 0.0
            nlen = len(norm)
            # Length pre-filter: ratio = 2*M / (la + lb) and M <= min(la, lb), so
            # for ratio >= REVIEW_RATIO we need max(la, lb) / min(la, lb) <= 2/REVIEW_RATIO - 1.
            # With REVIEW_RATIO = 0.78 → length ratio bound ≈ 1.56. We round to 1.6.
            max_len_ratio = 2.0 / REVIEW_RATIO - 1.0
            for cid, rec in self.records.items():
                if norm in rec.excludes:
                    continue
                for variant in rec.variants:
                    vlen = len(variant)
                    if vlen == 0:
                        continue
                    if max(nlen, vlen) / min(nlen, vlen) > max_len_ratio:
                        continue  # too different in length — can't possibly meet ratio threshold
                    score = fuzzy_ratio(norm, variant)
                    if score > best_score:
                        best_score = score
                        best_cid = cid
            if best_cid:
                if best_score >= AUTO_MERGE_RATIO:
                    self._record_variant(best_cid, norm)
                    self.cache[raw_name] = best_cid
                    return best_cid, "fuzzy"
                elif best_score >= REVIEW_RATIO:
                    # Queue for human review; meanwhile treat as a new canonical
                    self._queue_for_review(raw_name, norm, best_cid, best_score)
                    cid = self._mint_new_canonical(raw_name, norm)
                    self.cache[raw_name] = cid
                    return cid, "review"

        # 4. No match → new canonical
        cid = self._mint_new_canonical(raw_name, norm)
        self.cache[raw_name] = cid
        return cid, "new"

    def _record_variant(self, cid: str, normalized: str):
        rec = self.records[cid]
        rec.variants.add(normalized)
        self.normalized_index[normalized] = cid

    def _queue_for_review(self, raw_name, norm, suggested_cid, score):
        if raw_name in self.review_queue:
            self.review_queue[raw_name].seen_count += 1
        else:
            self.review_queue[raw_name] = ReviewEntry(
                raw_name=raw_name, normalized=norm,
                suggested_canonical=suggested_cid, score=score,
            )

    def _mint_new_canonical(self, raw_name, normalized):
        """Create a canonical_id from a normalized name. Uses the normalized form as
        the slug, or appends a numeric suffix if there's a collision."""
        slug_base = re.sub(r'[^a-z0-9]+', '_', normalized).strip('_') or 'player'
        slug = slug_base
        n = 2
        while slug in self.records:
            slug = f"{slug_base}_{n}"
            n += 1
        # Clean the raw form for display — strip color codes / escape sequences while
        # preserving capitalization. Falls back to raw if cleaning yields empty.
        display = clean_for_display(raw_name) or raw_name
        rec = CanonicalRecord(
            canonical_id=slug, display=display, variants={normalized},
        )
        self.records[slug] = rec
        self.normalized_index[normalized] = slug
        return slug

    def apply_reviews(self):
        """Process .review_queue.yaml: any 'accept' entries fold into their suggested canonical;
        'reject' entries are added to that canonical's `excludes` list. Returns counts."""
        n_accept = n_reject = 0
        for raw, entry in list(self.review_queue.items()):
            if entry.decision == "accept":
                target = entry.suggested_canonical
                if target in self.records:
                    self._record_variant(target, entry.normalized)
                    n_accept += 1
                    # If a tentative canonical was minted for this raw, fold + delete
                    old_cid = self.cache.get(raw)
                    if old_cid and old_cid != target and old_cid in self.records:
                        # Move all variants from old to target
                        for v in self.records[old_cid].variants:
                            self._record_variant(target, v)
                        del self.records[old_cid]
                    del self.review_queue[raw]
            elif entry.decision == "reject":
                target = entry.suggested_canonical
                if target in self.records:
                    self.records[target].excludes.add(entry.normalized)
                    n_reject += 1
                    del self.review_queue[raw]
        return n_accept, n_reject


# ─── CLI ────────────────────────────────────────────────────────────────
def _cli_test():
    """Quick test harness — runs a few example names through the canonicalizer."""
    c = Canonicalizer.load()
    samples = [
        # Plain forms
        ("Cronus", None), ("cronus", None), ("CRONUS", None),
        # Raw QW byte form (xantom archive)
        ("crïnus", None),
        # Pre-escaped form (our existing sync.py output)
        ("cr\\5onus", None), ("\\5Bance", None),
        # Excluded near-matches (in aliases.yaml)
        ("cronie", None), ("notCronus", None), ("Cronus's FANclub", None),
        # Brand new players
        ("blaze", None), ("BLooD_DoG", None),
    ]
    print(f"{'raw name':30}  {'normalized':25}  {'canonical_id':20}  decision")
    print('-' * 90)
    for raw, login in samples:
        cid, decision = c.resolve(raw, login)
        norm = normalize(raw)
        print(f"{raw!r:30}  {norm!r:25}  {cid:20}  {decision}")
    print()
    print(f"Review queue: {len(c.review_queue)} entries")
    for e in c.review_queue.values():
        print(f"  {e.raw_name!r:30}  → {e.suggested_canonical!r}  (score {e.score:.2f})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("test")
    sub.add_parser("apply-reviews", help="Process accepts/rejects in .review_queue.yaml back into aliases.yaml")
    args = parser.parse_args()
    if args.cmd == "apply-reviews":
        c = Canonicalizer.load()
        a, r = c.apply_reviews()
        c.save_aliases()
        c.save_review_queue()
        print(f"Applied {a} accept(s), {r} reject(s). aliases.yaml + .review_queue.yaml updated.")
    else:
        _cli_test()
