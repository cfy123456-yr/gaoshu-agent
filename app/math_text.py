"""Normalize OCR and spoken Chinese math into plain SymPy input."""

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
    (
        re.compile(r"\\(?:sin|cos|tan|cot|sec|csc|log|ln|exp|lim)\b"),
        lambda match: match.group(0)[1:],
    ),
)

_FUNCTION_NAMES = (
    "arcsin",
    "arccos",
    "arctan",
    "arcsinh",
    "arccosh",
    "arctanh",
    "asinh",
    "acosh",
    "atanh",
    "asin",
    "acos",
    "atan",
    "sinh",
    "cosh",
    "tanh",
    "sin",
    "cos",
    "tan",
    "cot",
    "sec",
    "csc",
    "sqrt",
    "exp",
    "log",
    "ln",
    "abs",
)
_FUNCTION_PATTERN = "(?:" + "|".join(_FUNCTION_NAMES) + ")"
_CHINESE_NUMBERS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}
_POWER_WORDS = {
    "平方": "2",
    "二次方": "2",
    "立方": "3",
    "三次方": "3",
}
_EXPRESSION_ATOM = (
    rf"(?:{_FUNCTION_PATTERN}\s*\([^()\n]*\)"
    r"|\([^()\n]*\)"
    r"|[A-Za-z][A-Za-z0-9_]*"
    r"|\d+(?:\.\d+)?)"
)
_SPOKEN_DIVIDE_RE = re.compile(r"\s*(?:除以|除上|比上)\s*")
_SPOKEN_MULTIPLY_RE = re.compile(r"\s*(?:乘以|乘上)\s*")
_SPOKEN_ADD_RE = re.compile(
    r"(?<=[A-Za-z0-9_)^])\s*加上?\s*(?=[A-Za-z0-9_(]|根号)"
)
_SPOKEN_SUBTRACT_RE = re.compile(
    r"(?<=[A-Za-z0-9_)^])\s*减去?\s*(?=[A-Za-z0-9_(]|根号)"
)
_SPOKEN_POWER_RE = re.compile(
    rf"(?P<base>{_EXPRESSION_ATOM})\s*的?\s*"
    r"(?P<power>平方|二次方|立方|三次方|"
    r"负?[一二两三四五六七八九十]+次方|负?\d+次方)(?![根号])"
)
_SPOKEN_FRACTION_RE = re.compile(
    rf"(?P<base>{_EXPRESSION_ATOM})\s*分之一"
)
_CHINESE_FRACTION_RE = re.compile(
    r"(?P<denominator>[一二两三四五六七八九十]+)\s*分之\s*"
    r"(?P<numerator>[一二两三四五六七八九十]+)"
)
_LEADING_BOUND_INTEGRAL_RE = re.compile(
    r"(?P<lower>-?(?:\d+(?:\.\d+)?|oo|pi))\s*(?:到|至)\s*"
    r"(?P<upper>-?(?:\d+(?:\.\d+)?|oo|pi))\s+"
    r"(?P<expr>[A-Za-z0-9_+\-*/^(). ]+?)\s*"
    r"的(?:定积分|积分)(?=$|[，,;；。！？!?])"
)
_INFINITY_CONCEPT_RE = re.compile(
    r"无穷级数|无穷小|无穷大量|无穷远|无穷多"
)
_FUNCTION_CALL_RE = re.compile(
    rf"(?<![A-Za-z])(?P<name>{_FUNCTION_PATTERN})\s*\("
)


def normalize_math_text(value: str) -> str:
    """Convert common Unicode, LaTeX, OCR, and spoken math to plain text."""
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
    text = _replace_unicode_square_roots(text)

    text = _normalize_infinity_terms(text)
    text = _normalize_spoken_math(text)
    text = _normalize_function_arguments(text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _replace_unicode_square_roots(value: str) -> str:
    pattern = re.compile(
        r"\u221a\s*(?:"
        r"\((?P<parenthesized>[^()\n]+)\)"
        r"|(?P<number>\d+(?:\.\d+)?)"
        r"|(?P<variable>[A-Za-z](?:\^[A-Za-z0-9_-]+)?)"
        r")"
    )

    def replace(match: re.Match[str]) -> str:
        argument = next(
            group
            for group in match.groups()
            if group is not None
        )
        rendered = f"sqrt({argument})"
        if (
            match.end() < len(value)
            and re.match(r"[A-Za-z0-9(]", value[match.end()])
        ):
            rendered += "*"
        return rendered

    return pattern.sub(replace, value)


def _normalize_infinity_terms(value: str) -> str:
    protected: list[str] = []

    def protect(match: re.Match[str]) -> str:
        placeholder = f"__infinity_concept_{len(protected)}__"
        protected.append(match.group(0))
        return placeholder

    text = _INFINITY_CONCEPT_RE.sub(protect, value)
    text = text.replace("正无穷大", "oo").replace("正无穷", "oo")
    text = text.replace("负无穷大", "-oo").replace("负无穷", "-oo")
    text = text.replace("无穷大", "oo")
    text = re.sub(r"无穷(?!(?:小|级数|远|多|大量|大))", "oo", text)

    for index, original in enumerate(protected):
        text = text.replace(
            f"__infinity_concept_{index}__",
            original,
        )
    return text


def _normalize_spoken_math(value: str) -> str:
    text = value
    text = text.replace("左括号", "(").replace("右括号", ")")
    text = _replace_function_shorthand(text)
    text = text.replace("乘方", "__power__")
    text = _SPOKEN_MULTIPLY_RE.sub("*", text)
    text = _SPOKEN_DIVIDE_RE.sub("/", text)
    text = text.replace("__power__", "乘方")

    text = _CHINESE_FRACTION_RE.sub(_replace_chinese_fraction, text)
    text = _SPOKEN_POWER_RE.sub(_replace_spoken_power, text)
    text = _SPOKEN_FRACTION_RE.sub(_replace_spoken_fraction, text)
    text = _SPOKEN_ADD_RE.sub("+", text)
    text = _SPOKEN_SUBTRACT_RE.sub("-", text)
    text = _replace_cube_roots(text)
    text = _replace_square_roots(text)
    text = _LEADING_BOUND_INTEGRAL_RE.sub(_replace_leading_bound_integral, text)
    return text


def _replace_function_shorthand(value: str) -> str:
    function_re = re.compile(
        rf"(?<![A-Za-z]){_FUNCTION_PATTERN}(?!\s*\()"
        r"(?:\s*\^\s*(?P<power>[-+]?\d+))?\s*"
        r"(?P<arg>[A-Za-z0-9_(][A-Za-z0-9_^+\-*/().]*?)"
        r"(?=(?:\s|$|[，,;；。！？!?]|除以|乘以|的))"
    )

    def replace(match: re.Match[str]) -> str:
        function_name = match.group(0).lstrip()
        name_match = re.match(rf"({_FUNCTION_PATTERN})", function_name)
        if name_match is None:
            return match.group(0)
        name = name_match.group(1)
        arg = match.group("arg").strip()
        if arg == "(" or arg.startswith(name + "("):
            return match.group(0)
        if arg.startswith("(") and arg.endswith(")"):
            rendered_arg = arg[1:-1].strip()
        else:
            rendered_arg = arg
        rendered_arg = _insert_implicit_multiplication(rendered_arg)
        power = match.group("power")
        rendered = f"{name}({rendered_arg})"
        if power:
            rendered += f"^({power})" if power.startswith("-") else f"^{power}"
        return rendered

    text = function_re.sub(replace, value)
    text = re.sub(
        rf"(?<![A-Za-z])(?P<function>{_FUNCTION_PATTERN})(?!\s*\()\s+"
        r"(?P<arg>[A-Za-z0-9_]+(?:\^[A-Za-z0-9_-]+)?)",
        lambda match: (
            f"{match.group('function')}"
            f"({_insert_implicit_multiplication(match.group('arg'))})"
        ),
        text,
    )
    return text


def _insert_implicit_multiplication(value: str) -> str:
    text = re.sub(r"(?<=\d)(?=[A-Za-z(])", "*", value)
    text = re.sub(r"(?<=\))(?=[A-Za-z0-9(])", "*", text)
    return _insert_multiplication_before_parentheses(text)


def _insert_multiplication_before_parentheses(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        prefix = value[: match.start() + 1]
        identifier_match = re.search(r"[A-Za-z][A-Za-z0-9_]*$", prefix)
        if (
            identifier_match is not None
            and identifier_match.group(0) in _FUNCTION_NAMES
        ):
            return match.group(0)
        return "*("

    return re.sub(r"[A-Za-z]\(", replace, value)


def _normalize_function_arguments(value: str) -> str:
    """Canonicalize multiplication inside known function arguments."""
    text = value
    cursor = 0
    rendered: list[str] = []

    while cursor < len(text):
        match = _FUNCTION_CALL_RE.search(text, cursor)
        if match is None:
            rendered.append(text[cursor:])
            break

        open_index = match.end() - 1
        close_index = _matching_parenthesis(text, open_index)
        if close_index is None:
            rendered.append(text[cursor:])
            break

        rendered.append(text[cursor : match.start()])
        rendered.append(f"{match.group('name')}(")
        argument = text[match.end() : close_index]
        argument = _normalize_function_arguments(argument)
        argument = re.sub(r"\s+", "", argument)
        rendered.append(f"{_insert_implicit_multiplication(argument)})")
        cursor = close_index + 1

    return "".join(rendered)


def _matching_parenthesis(value: str, open_index: int) -> int | None:
    depth = 0
    for index in range(open_index, len(value)):
        if value[index] == "(":
            depth += 1
        elif value[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def _replace_cube_roots(value: str) -> str:
    pattern = re.compile(
        r"(?:三次|立方)\s*根号\s*(?:下)?\s*"
        r"(?P<arg>\([^()\n]+\)|[A-Za-z0-9_+\-*/^(). ]+?)"
        r"(?=\s*(?:的|$|[，,;；。！？!?]"
        r"|\+(?=\s*根号)|-(?=\s*根号)))"
    )

    def replace(match: re.Match[str]) -> str:
        arg = _clean_root_argument(match.group("arg"))
        return f"({arg})^(1/3)"

    return pattern.sub(replace, value)


def _replace_square_roots(value: str) -> str:
    pattern = re.compile(
        r"根号\s*(?:下)?\s*"
        r"(?P<arg>\([^()\n]+\)|[A-Za-z0-9_+\-*/^(). ]+?)"
        r"(?=\s*(?:的|$|[，,;；。！？!?]"
        r"|\+(?=\s*根号)|-(?=\s*根号)))"
    )

    def replace(match: re.Match[str]) -> str:
        arg = _clean_root_argument(match.group("arg"))
        return f"sqrt({arg})"

    return pattern.sub(replace, value)


def _clean_root_argument(value: str) -> str:
    arg = value.strip()
    if arg.startswith("(") and arg.endswith(")"):
        arg = arg[1:-1].strip()
    return _insert_implicit_multiplication(arg)


def _replace_spoken_power(match: re.Match[str]) -> str:
    base = match.group("base").strip()
    word = match.group("power")
    if word in _POWER_WORDS:
        exponent = _POWER_WORDS[word]
    else:
        exponent_text = word.removesuffix("次方")
        negative = exponent_text.startswith("负")
        if negative:
            exponent_text = exponent_text[1:]
        if exponent_text.isdigit():
            exponent = exponent_text
        else:
            exponent = str(_CHINESE_NUMBERS.get(exponent_text, exponent_text))
        if negative:
            exponent = f"-{exponent}"
    if exponent.startswith("-"):
        return f"{base}^({exponent})"
    return f"{base}^{exponent}"


def _replace_spoken_fraction(match: re.Match[str]) -> str:
    return f"1/({match.group('base').strip()})"


def _replace_chinese_fraction(match: re.Match[str]) -> str:
    numerator = _CHINESE_NUMBERS.get(match.group("numerator"))
    denominator = _CHINESE_NUMBERS.get(match.group("denominator"))
    if numerator is None or denominator is None:
        return match.group(0)
    return f"({numerator}/{denominator})"


def _replace_leading_bound_integral(match: re.Match[str]) -> str:
    expression = match.group("expr").strip()
    return (
        f"{expression} 在 {match.group('lower')} 到 "
        f"{match.group('upper')} 的定积分"
    )


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
