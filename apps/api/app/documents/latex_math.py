"""A small LaTeX math subset → MathML (HTML preview) and OMML (native PowerPoint equations).

Only the constructs that appear in reports and theses are supported: identifiers,
numbers, operators, Greek letters and common symbols, ``^``/``_`` scripts,
``\\frac``, ``\\sqrt`` (with optional index), ``\\sum``/``\\prod``/``\\int`` with
limits, ``\\left…\\right`` delimiters, ``\\text{}``, ``\\mathrm{}`` and ``\\operatorname{}``.
Anything else raises :class:`LatexError`, and callers keep the original text,
so an unsupported formula never turns into a wrong equation.

Formulas are written in slide text as ``$$…$$``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import escape
from xml.sax.saxutils import escape as xml_escape

MATH_SPAN_RE = re.compile(r"\$\$([^$]{1,400})\$\$")

SYMBOLS = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε", "zeta": "ζ",
    "eta": "η", "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν",
    "xi": "ξ", "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ", "varphi": "φ",
    "chi": "χ", "psi": "ψ", "omega": "ω", "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}
OPERATORS = {
    "times": "×", "cdot": "⋅", "pm": "±", "mp": "∓", "div": "÷", "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥",
    "neq": "≠", "ne": "≠", "approx": "≈", "equiv": "≡", "sim": "∼", "propto": "∝", "infty": "∞",
    "rightarrow": "→", "to": "→", "leftarrow": "←", "Rightarrow": "⇒", "Leftrightarrow": "⇔", "in": "∈",
    "notin": "∉", "subset": "⊂", "subseteq": "⊆", "cup": "∪", "cap": "∩", "partial": "∂", "nabla": "∇",
    "ldots": "…", "cdots": "⋯", "forall": "∀", "exists": "∃", "circ": "∘", "ast": "∗", "mid": "∣",
    "log": "log", "ln": "ln", "exp": "exp", "sin": "sin", "cos": "cos", "tan": "tan", "max": "max",
    "min": "min", "lim": "lim", "arg": "arg",
}
FUNCTION_NAMES = {"log", "ln", "exp", "sin", "cos", "tan", "max", "min", "lim", "arg"}
BIG_OPERATORS = {"sum": "∑", "prod": "∏", "int": "∫", "iint": "∬", "oint": "∮"}
ACCENTS = {"hat": "^", "bar": "¯", "vec": "→", "tilde": "~", "dot": "˙"}
DELIMITERS = {"(": "(", ")": ")", "[": "[", "]": "]", "\\{": "{", "\\}": "}", "|": "|", ".": "", "\\langle": "⟨", "\\rangle": "⟩"}


class LatexError(ValueError):
    pass


@dataclass
class Node:
    kind: str  # row, mi, mn, mo, mtext, frac, sup, sub, subsup, sqrt, nary, fenced
    text: str = ""
    children: list[Node] = field(default_factory=list)


TOKEN_RE = re.compile(r"\\[A-Za-z]+|\\[{}|,;! ]|[A-Za-z]|\d+(?:\.\d+)?|\S")


class _Parser:
    def __init__(self, source: str):
        self.tokens = TOKEN_RE.findall(source)
        self.position = 0

    def peek(self) -> str | None:
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def take(self) -> str:
        token = self.peek()
        if token is None:
            raise LatexError("公式意外结束")
        self.position += 1
        return token

    def expect(self, token: str) -> None:
        if self.take() != token:
            raise LatexError(f"缺少 {token}")

    def parse(self) -> Node:
        node = self.row(stop=set())
        if self.peek() is not None:
            raise LatexError(f"无法解析 {self.peek()}")
        return node

    def row(self, stop: set[str]) -> Node:
        items: list[Node] = []
        while (token := self.peek()) is not None and token not in stop:
            if token == "\\right":
                break
            item = self.scripted()
            if item.kind == "nary" and self.peek() not in stop and self.peek() not in {None, "\\right"}:
                # A big operator owns the term that follows it (∑ x_i, ∫ f(x) dx).
                item.children[2] = Node("row", children=[self.scripted()])
            items.append(item)
        return Node("row", children=items)

    def group(self) -> Node:
        if self.peek() == "{":
            self.take()
            node = self.row(stop={"}"})
            self.expect("}")
            return node
        return self.atom()

    def raw_group(self) -> str:
        self.expect("{")
        depth, parts = 1, []
        while True:
            token = self.take()
            if token == "{":
                depth += 1
            elif token == "}":
                depth -= 1
                if depth == 0:
                    break
            parts.append(token)
        return "".join(part if not part.startswith("\\") else part[1:] for part in parts)

    def scripted(self) -> Node:
        base = self.atom()
        sub = sup = None
        while self.peek() in {"^", "_"}:
            marker = self.take()
            value = self.group()
            if marker == "^":
                if sup is not None:
                    raise LatexError("重复上标")
                sup = value
            else:
                if sub is not None:
                    raise LatexError("重复下标")
                sub = value
        if base.kind == "nary":
            base.children = [sub or Node("row"), sup or Node("row"), Node("row")]
            return base
        if sub is not None and sup is not None:
            return Node("subsup", children=[base, sub, sup])
        if sup is not None:
            return Node("sup", children=[base, sup])
        if sub is not None:
            return Node("sub", children=[base, sub])
        return base

    def atom(self) -> Node:
        token = self.take()
        if token == "{":
            node = self.row(stop={"}"})
            self.expect("}")
            return node
        if token.startswith("\\"):
            name = token[1:]
            if name == "frac":
                return Node("frac", children=[self.group(), self.group()])
            if name == "sqrt":
                index = None
                if self.peek() == "[":
                    self.take()
                    index = self.row(stop={"]"})
                    self.expect("]")
                body = self.group()
                return Node("sqrt", children=[body, *([index] if index else [])])
            if name in {"text", "mathrm", "operatorname", "textrm"}:
                return Node("mtext" if name in {"text", "textrm"} else "mi-upright", text=self.raw_group())
            if name == "left":
                opening = self.take()
                opening = opening if opening != "\\" else self.take()
                body = self.row(stop=set())
                self.expect("\\right")
                closing = self.take()
                if opening not in DELIMITERS or closing not in DELIMITERS:
                    raise LatexError("不支持的括号")
                return Node("fenced", text=DELIMITERS[opening] + "|" + DELIMITERS[closing], children=[body])
            if name in BIG_OPERATORS:
                return Node("nary", text=BIG_OPERATORS[name])
            if name in SYMBOLS:
                return Node("mi", text=SYMBOLS[name])
            if name in FUNCTION_NAMES:
                return Node("mi-upright", text=name)
            if name in OPERATORS:
                return Node("mo", text=OPERATORS[name])
            if name in {",", ";", "!", " "}:
                return Node("mo", text=" " if name != "!" else "")
            if name in {"{", "}"}:
                return Node("mo", text=name)
            if name == "|":
                return Node("mo", text="‖")
            if name in ACCENTS:
                return Node("accent", text=ACCENTS[name], children=[self.group()])
            raise LatexError(f"不支持的命令 \\{name}")
        if re.fullmatch(r"\d+(?:\.\d+)?", token):
            return Node("mn", text=token)
        if re.fullmatch(r"[A-Za-z]", token):
            return Node("mi", text=token)
        if token in "+-=<>/*,.;:!?()[]|'":
            return Node("mo", text={"-": "−", "*": "∗"}.get(token, token))
        if token in {"}", "^", "_", "&", "#", "%", "$"}:
            raise LatexError(f"无法解析 {token}")
        return Node("mo", text=token)


def parse_latex(source: str) -> Node:
    source = source.strip()
    if not source:
        raise LatexError("空公式")
    return _Parser(source).parse()


# ---------------------------------------------------------------- MathML


def _mathml(node: Node) -> str:
    kind, children = node.kind, node.children
    if kind == "row":
        inner = "".join(_mathml(child) for child in children)
        return inner if len(children) == 1 else f"<mrow>{inner}</mrow>"
    if kind == "mi":
        return f"<mi>{escape(node.text)}</mi>"
    if kind == "mi-upright":
        return f'<mi mathvariant="normal">{escape(node.text)}</mi>'
    if kind == "mn":
        return f"<mn>{escape(node.text)}</mn>"
    if kind == "mo":
        return f"<mo>{escape(node.text)}</mo>" if node.text.strip() else '<mspace width="0.2em"></mspace>'
    if kind == "mtext":
        return f"<mtext>{escape(node.text)}</mtext>"
    if kind == "frac":
        return f"<mfrac>{_mathml(children[0])}{_mathml(children[1])}</mfrac>"
    if kind == "sup":
        return f"<msup>{_mathml(children[0])}{_mathml(children[1])}</msup>"
    if kind == "sub":
        return f"<msub>{_mathml(children[0])}{_mathml(children[1])}</msub>"
    if kind == "subsup":
        return f"<msubsup>{''.join(_mathml(child) for child in children)}</msubsup>"
    if kind == "sqrt":
        if len(children) == 2:
            return f"<mroot>{_mathml(children[0])}{_mathml(children[1])}</mroot>"
        return f"<msqrt>{_mathml(children[0])}</msqrt>"
    if kind == "nary":
        sub, sup = (children + [Node("row"), Node("row")])[:2]
        body = _mathml(children[2]) if len(children) > 2 and children[2].children else ""
        operator = f'<mo largeop="true">{escape(node.text)}</mo>'
        if sub.children and sup.children:
            return f"<mrow><munderover>{operator}{_mathml(sub)}{_mathml(sup)}</munderover>{body}</mrow>"
        if sub.children:
            return f"<mrow><munder>{operator}{_mathml(sub)}</munder>{body}</mrow>"
        return f"<mrow>{operator}{body}</mrow>"
    if kind == "accent":
        return f'<mover accent="true">{_mathml(children[0])}<mo>{escape(node.text)}</mo></mover>'
    if kind == "fenced":
        opening, closing = node.text.split("|", 1) if node.text != "|||" else ("|", "|")
        left = f'<mo fence="true">{escape(opening)}</mo>' if opening else ""
        right = f'<mo fence="true">{escape(closing)}</mo>' if closing else ""
        return f"<mrow>{left}{_mathml(children[0])}{right}</mrow>"
    raise LatexError(kind)


def to_mathml(source: str, display: bool = False) -> str:
    body = _mathml(parse_latex(source))
    mode = "block" if display else "inline"
    return f'<math xmlns="http://www.w3.org/1998/Math/MathML" display="{mode}">{body}</math>'


# ---------------------------------------------------------------- OMML

M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _run(text: str, italic: bool, size: int | None) -> str:
    size_attr = f' sz="{size}"' if size else ""
    italic_attr = ' i="1"' if italic else ' i="0"'
    return (
        f'<m:r><a:rPr lang="en-US"{italic_attr}{size_attr}><a:latin typeface="Cambria Math" panose="02040503050406030204" '
        f'pitchFamily="18" charset="0"/><a:cs typeface="Cambria Math"/></a:rPr><m:t>{xml_escape(text)}</m:t></m:r>'
    )


def _omml(node: Node, size: int | None) -> str:
    kind, children = node.kind, node.children
    if kind == "row":
        return "".join(_omml(child, size) for child in children)
    if kind == "mi":
        return _run(node.text, italic=len(node.text) == 1 and node.text.isascii(), size=size)
    if kind in {"mi-upright", "mn", "mtext"}:
        return _run(node.text, italic=False, size=size)
    if kind == "mo":
        return _run(node.text or " ", italic=False, size=size)
    if kind == "frac":
        return f"<m:f><m:num>{_omml(children[0], size)}</m:num><m:den>{_omml(children[1], size)}</m:den></m:f>"
    if kind == "sup":
        return f"<m:sSup><m:e>{_omml(children[0], size)}</m:e><m:sup>{_omml(children[1], size)}</m:sup></m:sSup>"
    if kind == "sub":
        return f"<m:sSub><m:e>{_omml(children[0], size)}</m:e><m:sub>{_omml(children[1], size)}</m:sub></m:sSub>"
    if kind == "subsup":
        base, sub, sup = children
        return (f"<m:sSubSup><m:e>{_omml(base, size)}</m:e><m:sub>{_omml(sub, size)}</m:sub>"
                f"<m:sup>{_omml(sup, size)}</m:sup></m:sSubSup>")
    if kind == "sqrt":
        if len(children) == 2:
            return f"<m:rad><m:deg>{_omml(children[1], size)}</m:deg><m:e>{_omml(children[0], size)}</m:e></m:rad>"
        return f'<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/><m:e>{_omml(children[0], size)}</m:e></m:rad>'
    if kind == "nary":
        sub, sup = (children + [Node("row"), Node("row")])[:2]
        hide = ('<m:subHide m:val="1"/>' if not sub.children else "") + ('<m:supHide m:val="1"/>' if not sup.children else "")
        return (f'<m:nary><m:naryPr><m:chr m:val="{node.text}"/><m:limLoc m:val="undOvr"/>{hide}</m:naryPr>'
                f"<m:sub>{_omml(sub, size)}</m:sub><m:sup>{_omml(sup, size)}</m:sup>"
                f"<m:e>{_omml(children[2], size) if len(children) > 2 else ''}</m:e></m:nary>")
    if kind == "accent":
        return f'<m:acc><m:accPr><m:chr m:val="{xml_escape(node.text)}"/></m:accPr><m:e>{_omml(children[0], size)}</m:e></m:acc>'
    if kind == "fenced":
        opening, closing = node.text.split("|", 1) if node.text != "|||" else ("|", "|")
        return (f'<m:d><m:dPr><m:begChr m:val="{xml_escape(opening)}"/><m:endChr m:val="{xml_escape(closing)}"/></m:dPr>'
                f"<m:e>{_omml(children[0], size)}</m:e></m:d>")
    raise LatexError(kind)


def to_omml(source: str, size_hundredths: int | None = None) -> str:
    """``<m:oMath>`` fragment using the ``m:``/``a:`` prefixes (declared by the caller)."""
    return f"<m:oMath>{_omml(parse_latex(source), size_hundredths)}</m:oMath>"


SUPERSCRIPT = str.maketrans("0123456789+-=()nijkN", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱʲᵏᴺ")
SUBSCRIPT = str.maketrans("0123456789+-=()aeijknmoprstux", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑᵢⱼₖₙₘₒₚᵣₛₜᵤₓ")


def _script(text: str, table: dict, marker: str) -> str:
    text = text.replace(" ", "")
    plain = text.replace("−", "-")
    converted = plain.translate(table)
    if all(char != original or char in "()" for char, original in zip(converted, plain, strict=True)):
        return converted
    return f"{marker}({text})" if len(text) > 1 else f"{marker}{text}"


def _linear(node: Node) -> str:
    kind, children = node.kind, node.children
    if kind == "row":
        return "".join(_linear(child) for child in children)
    if kind in {"mi", "mi-upright", "mn", "mtext"}:
        return node.text
    if kind == "mo":
        return f" {node.text} " if node.text in {"=", "≤", "≥", "≠", "≈", "→", "⇒", "∈"} else node.text
    if kind == "frac":
        top, bottom = _linear(children[0]), _linear(children[1])
        wrap = lambda value: value if re.fullmatch(r"[\w.]+", value) else f"({value})"
        return f"{wrap(top)}/{wrap(bottom)}"
    if kind == "sup":
        return _linear(children[0]) + _script(_linear(children[1]), SUPERSCRIPT, "^")
    if kind == "sub":
        return _linear(children[0]) + _script(_linear(children[1]), SUBSCRIPT, "_")
    if kind == "subsup":
        return _linear(children[0]) + _script(_linear(children[1]), SUBSCRIPT, "_") + _script(_linear(children[2]), SUPERSCRIPT, "^")
    if kind == "sqrt":
        body = _linear(children[0])
        root = "√" if len(children) == 1 else {"3": "∛", "4": "∜"}.get(_linear(children[1]), f"{_linear(children[1])}√")
        return root + (body if len(body) == 1 else f"({body})")
    if kind == "nary":
        sub, sup = (children + [Node("row"), Node("row")])[:2]
        body = _linear(children[2]) if len(children) > 2 else ""
        result = node.text
        if sub.children:
            result += _script(_linear(sub), SUBSCRIPT, "_")
        if sup.children:
            result += _script(_linear(sup), SUPERSCRIPT, "^")
        return result + body
    if kind == "fenced":
        opening, closing = node.text.split("|", 1) if node.text != "|||" else ("|", "|")
        return f"{opening}{_linear(children[0])}{closing}"
    if kind == "accent":
        base = _linear(children[0])
        mark = {"^": "\u0302", "¯": "\u0304", "→": "\u20D7", "~": "\u0303", "˙": "\u0307"}.get(node.text, "")
        return base + mark if len(base) == 1 else base
    raise LatexError(kind)


def to_linear(source: str) -> str:
    """Readable single-line Unicode form (fallback text where equations are unsupported)."""
    return re.sub(r"\s{2,}", " ", _linear(parse_latex(source))).strip()


def math_segments(text: str) -> list[tuple[str, str]]:
    """Split text into ("text", …) and ("math", latex) segments."""
    segments: list[tuple[str, str]] = []
    last = 0
    for match in MATH_SPAN_RE.finditer(text):
        if match.start() > last:
            segments.append(("text", text[last:match.start()]))
        segments.append(("math", match.group(1)))
        last = match.end()
    if last < len(text):
        segments.append(("text", text[last:]))
    return segments


def attach_slide_math(slide: dict) -> int:
    """Store MathML for every supported ``$$…$$`` formula of a slide in ``slide["math"]``.

    ``math`` is derived from the slide copy, so it is deliberately outside the render
    stamp fields; the engine only uses it to draw formulas that are already in the text.
    """
    content = slide.get("content") or {}
    texts = [str(content.get("title", "")), str(slide.get("message", "")), *map(str, content.get("bullets") or [])]
    rendered: dict[str, str] = {}
    for text in texts:
        for match in MATH_SPAN_RE.finditer(text):
            latex = match.group(1)
            if latex in rendered:
                continue
            try:
                rendered[latex] = to_mathml(latex)
            except LatexError:
                continue
    if rendered:
        slide["math"] = [{"latex": latex, "mathml": mathml} for latex, mathml in rendered.items()]
    else:
        slide.pop("math", None)
    return len(rendered)
