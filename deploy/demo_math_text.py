"""Normalize common math notation returned by OCR providers."""

from __future__ import annotations

import re


_CHAR_REPLACEMENTS = str.maketrans(
    {
        "\u2212": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\uff0d": "-",
        "\u00d7": "*",
        "\u00b7": "*",
        "\u22c5": "*",
        "\u00f7": "/",
        "\u2215": "/",
        "\u2044": "/",
        "\u03c0": "pi",
        "\u221e": "oo",
        "\u2192": "->",
        "\u21d2": "=>",
        "\uff08": "(",
        "\uff09": ")",
        "\uff0c": ",",
        "\uff1a": ":",
        "\uff1b": ";",
        "\u201c": '"',
        "\u201d": '"',
        "\u2018": "'",
        "\u2019": "'",
    }
)

_SUPERSCRIPT_MAP = {
    "\u2070": "0",
    "\u00b9": "1",
    "\u00b2": "2",
    "\u00b3": "3",
    "\u2074": "4",
    "\u2075": "5",
    "\u2076": "6",
    "\u2077": "7",
    "\u2078": "8",
    "\u2079": "9",
    "\u207a": "+",
    "\u207b": "-",
    "\u207c": "=",
    "\u207d": "(",
    "\u207e": ")",
    "\u207f": "n",
    "\u2071": "i",
}

_SUBSCRIPT_MAP = {
    "\u2080": "0",
    "\u2081": "1",
    "\u2082": "2",
    "\u2083": "3",
    "\u2084": "4",
    "\u2085": "5",
    "\u2086": "6",
    "\u2087": "7",
    "\u2088": "8",
    "\u2089": "9",
    "\u208a": "+",
    "\u208b": "-",
    "\u208c": "=",
    "\u208d": "(",
    "\u208e": ")",
    "\u2090": "a",
    "\u2091": "e",
    "\u2095": "h",
    "\u1d62": "i",
    "\u2c7c": "j",
    "\u2096": "k",
    "\u2097": "l",
    "\u2098": "m",
    "\u2099": "n",
    "\u2092": "o",
    "\u209a": "p",
    "\u1d63": "r",
    "\u209b": "s",
    "\u209c": "t",
    "\u2093": "x",
}

_SUPERSCRIPT_RE = re.compile("[" + re.escape("".join(_SUPERSCRIPT_MAP)) + "]+")
_SUBSCRIPT_RE = re.compile("[" + re.escape("".join(_SUBSCRIPT_MAP)) + "]+")
_LATEX_FRACTION_RE = re.compile(
    r"\\frac\s*\{([^{}\n]+)\}\s*\{([^{}\n]+)\}"
)
_LATEX_SYMBOL_REPLACEMENTS = (
    (re.compile(r"\\left\b|\\right\b"), ""),
    (re.compile(r"\\times\b|\\cdot\b"), "*"),
    (re.compile(r"\\div\b"), "/"),
    (re.compile(r"\\pi\b"), "pi"),
    (re.compile(r"\\infty\b"), "oo"),
    (re.compile(r"\\to\b"), "->"),
    (re.compile(r"\\(?:sin|cos|tan|cot|sec|csc|log|ln|exp|lim)\b"), lambda m: m.group(0)[1:]),
)


def normalize_math_text(value: str) -> str:
    """Convert common Unicode and LaTeX OCR output to plain math text."""
    if not value:
        return ""

    text = str(value).replace("\x00", "").replace("\ufeff", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.translate(_CHAR_REPLACEMENTS)

    text = _SUPERSCRIPT_RE.sub(
        lambda match: "^" + "".join(_SUPERSCRIPT_MAP[ch] for ch in match.group(0)),
        text,
    )
    text = _SUBSCRIPT_RE.sub(
        lambda match: "_" + "".join(_SUBSCRIPT_MAP[ch] for ch in match.group(0)),
        text,
    )

    text = _replace_latex_fractions(text)
    for pattern, replacement in _LATEX_SYMBOL_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    text = re.sub(r"\^\s*\{([^{}\n]+)\}", r"^\1", text)
    text = re.sub(r"_\s*\{([^{}\n]+)\}", r"_\1", text)
    text = re.sub(r"\\sqrt\s*\{([^{}\n]+)\}", r"sqrt(\1)", text)
    text = re.sub(r"\\sqrt\s*([A-Za-z0-9])", r"sqrt(\1)", text)
    text = re.sub(r"\\\[|\\\]|\\\(|\\\)", "", text)

    text = re.sub(r"\$\$(.*?)\$\$", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"(?<!\$)\$(?!\$)(.*?)\$(?!\$)", r"\1", text)
    text = re.sub(r"\u221a\s*\(([^()\n]+)\)", r"sqrt(\1)", text)
    text = re.sub(
        r"\u221a\s*([A-Za-z0-9]+(?:\^[A-Za-z0-9]+)?)",
        r"sqrt(\1)",
        text,
    )

    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _replace_latex_fractions(value: str) -> str:
    previous = None
    current = value
    while current != previous:
        previous = current
        current = _LATEX_FRACTION_RE.sub(
            lambda match: f"(({match.group(1)})/({match.group(2)}))",
            current,
        )
    return current
