"""Non-destructive Arabic tokenization, normalization, and spelling expansion."""

from __future__ import annotations

import unicodedata

from takhrij.models import Variant

TATWEEL = "\u0640"
ALEF_GROUP = ("ا", "أ", "إ", "آ")
HAMZATED_ALEFS = frozenset(("أ", "إ", "آ"))
ARTICLE_PROCLITICS = frozenset("وفبكلس")
PRONOMINAL_SUFFIXES = ("هما", "كما", "هم", "هن", "كم", "كن", "ها", "نا", "ه", "ك", "ي")


def is_arabic_letter(char: str) -> bool:
    return unicodedata.category(char).startswith("L") and "ARABIC" in unicodedata.name(char, "")


def is_arabic_mark(char: str) -> bool:
    return unicodedata.category(char).startswith("M") and "ARABIC" in unicodedata.name(char, "")


def normalize_token(raw: str) -> str:
    """Normalize scribal marks only; never collapse grammatical letters."""
    text = unicodedata.normalize("NFC", raw).replace(TATWEEL, "")
    return "".join(char for char in text if not is_arabic_mark(char))


def tokenize_with_offsets(raw_text: str) -> list[tuple[str, int, int]]:
    tokens: list[tuple[str, int, int]] = []
    start: int | None = None
    for index, char in enumerate(raw_text):
        if is_arabic_letter(char):
            if start is None:
                start = index
            continue
        if start is not None and is_arabic_mark(char):
            continue
        if start is not None:
            tokens.append((raw_text[start:index], start, index))
            start = None
    if start is not None:
        tokens.append((raw_text[start:], start, len(raw_text)))
    return tokens


def _is_article_alef(form: str, index: int) -> bool:
    if form[index : index + 2] != "ال":
        return False
    prefix = form[:index]
    return not prefix or (len(prefix) <= 2 and all(char in ARTICLE_PROCLITICS for char in prefix))


def _suffix_alef_positions(form: str, _display_form: str) -> frozenset[int]:
    """Return alef positions that belong to inflectional or pronominal suffixes.

    Surface spelling alone cannot resolve every Arabic morphological ambiguity,
    so this deliberately fails closed: terminal ``ات``, ``ان``, ``نا`` and a
    tanween-bearing accusative alef are protected rather than risk inventing an
    impossible spelling.
    """
    protected: set[int] = set()
    stem_end = len(form)

    pronoun = next(
        (
            suffix
            for suffix in PRONOMINAL_SUFFIXES
            if form.endswith(suffix) and len(form) > len(suffix) + 1
        ),
        None,
    )
    if pronoun is not None:
        stem_end -= len(pronoun)
        protected.update(
            position for position in range(stem_end, len(form)) if form[position] in ALEF_GROUP
        )
        # The dual nun is dropped before a possessive pronoun: تخريجانا.
        if stem_end and form[stem_end - 1] == "ا":
            protected.add(stem_end - 1)

    unpronominalized = form[:stem_end]
    if len(unpronominalized) > 2 and unpronominalized.endswith(("ات", "ان")):
        protected.add(stem_end - 2)

    # A bare final alef is morphologically ambiguous without full analysis. It
    # is commonly accusative tanween or part of an inflectional suffix, so fail
    # closed rather than manufacture a hamzated ending. This also covers both
    # Unicode orders used for written fathatan.
    if form.endswith("ا"):
        protected.add(len(form) - 1)

    return frozenset(protected)


def _expand_first_lexical_alef(
    form: str, *, protected_positions: frozenset[int] = frozenset()
) -> list[str]:
    """Strip one lexical hamza seat; never add hamza to a plain long alef."""
    index = next(
        (
            position
            for position, char in enumerate(form)
            if char in HAMZATED_ALEFS
            and position not in protected_positions
            and not _is_article_alef(form, position)
        ),
        None,
    )
    if index is None:
        return [form]
    return [form, form[:index] + "ا" + form[index + 1 :]]


def expand_orthographic_variants(form: str, max_variants: int = 64) -> list[str]:
    """Enumerate documented spelling alternatives without destructive conflation."""
    display_form = unicodedata.normalize("NFC", form).replace(TATWEEL, "")
    canonical = normalize_token(display_form)
    protected_positions = _suffix_alef_positions(canonical, display_form)
    bases = _expand_first_lexical_alef(canonical, protected_positions=protected_positions)
    expanded: list[str] = [display_form]
    for candidate in bases:
        expanded.append(candidate)
        if candidate.endswith("ى"):
            expanded.append(candidate[:-1] + "ي")
    result = list(dict.fromkeys(expanded))
    if len(result) > max_variants:
        raise ValueError(f"orthographic expansion exceeds MAX_VARIANTS={max_variants}")
    return result


def validate_variants(forms: list[str], max_variants: int = 64) -> list[str]:
    cleaned: list[str] = []
    for raw in forms:
        form = unicodedata.normalize("NFC", raw.strip())
        if not form or any(char.isspace() for char in form):
            raise ValueError("v1 variants must be non-empty single tokens")
        letters = [char for char in form if is_arabic_letter(char)]
        if len(letters) < 2 or any(
            not (is_arabic_letter(c) or is_arabic_mark(c) or c == TATWEEL) for c in form
        ):
            raise ValueError(f"malformed Arabic variant: {raw!r}")
        cleaned.append(form)
    unique = list(dict.fromkeys(cleaned))
    if len(unique) > max_variants:
        raise ValueError(f"variant count exceeds MAX_VARIANTS={max_variants}")
    return unique


def build_variant_set(
    original: str,
    morphological_forms: list[str],
    *,
    max_variants: int = 64,
) -> list[Variant]:
    validated = validate_variants([original, *morphological_forms], max_variants=max_variants)
    variants: list[Variant] = []
    seen: set[str] = set()
    for form in validated:
        source = "input" if form == original else "morphologist"
        for spelling in expand_orthographic_variants(form, max_variants=max_variants):
            if spelling in seen:
                continue
            seen.add(spelling)
            variants.append(Variant(spelling, source if spelling == form else "orthographic", form))
            if len(variants) > max_variants:
                raise ValueError(f"expanded variant count exceeds MAX_VARIANTS={max_variants}")
    return variants
