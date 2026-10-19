"""Conservative, geometry-backed recovery of horizontal PDF mathematics.

The normalizer owns character mapping; this module never guesses what a glyph means.
Only vector fraction bars and adjacent raised math characters supply layout evidence.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class _Glyph:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    baseline: float
    size: float
    block: int
    line: int
    order: int
    horizontal: bool = True
    recovered: bool = False

    @property
    def cx(self):
        return (self.x0 + self.x1) / 2

    @property
    def cy(self):
        return (self.y0 + self.y1) / 2


def _glyphs(page, normalize_character):
    result = []
    for bi, block in enumerate(page.get_text("rawdict")["blocks"]):
        for li, line in enumerate(block.get("lines", [])):
            horizontal = line.get("dir", (1, 0)) == (1, 0)
            for span in line["spans"]:
                for char in span["chars"]:
                    result.append(_Glyph(
                        normalize_character(char["c"], span["font"]),
                        *char["bbox"], char["origin"][1], span["size"],
                        bi, li, len(result), horizontal,
                    ))
    return result


def _bars(page):
    bars = []
    verticals = []
    for drawing in page.get_drawings():
        if drawing.get("type") not in {"s", "fs"}:
            continue
        for item in drawing["items"]:
            if item[0] != "l":
                continue
            p, q = item[1:3]
            if abs(p.x - q.x) < 0.3 and abs(p.y - q.y) > 2:
                verticals.append(((p.x + q.x) / 2, min(p.y, q.y), max(p.y, q.y)))
            if abs(p.y - q.y) > 0.3 or abs(p.x - q.x) < 2:
                continue
            bar = (min(p.x, q.x), max(p.x, q.x), (p.y + q.y) / 2)
            if not any(max(abs(a - b) for a, b in zip(bar, old, strict=True)) < 0.5 for old in bars):
                bars.append(bar)
    return [bar for bar in bars if not any(
        (abs(x - bar[0]) < 1 or abs(x - bar[1]) < 1) and y0 - 1 <= bar[2] <= y1 + 1
        for x, y0, y1 in verticals
    )]


def _math_row(row):
    return bool(row) and all(re.fullmatch(r"[0-9A-Za-z+−\-*/().]+", c.text) for c in row)


def _fraction_candidates(glyphs, bars):
    for x0, x1, y in bars:
        nearby = [c for c in glyphs if c.horizontal and c.text.strip()
                  and x0 - 0.12 * c.size <= c.cx <= x1 + 0.12 * c.size
                  and abs(c.cy - y) <= 1.0 * c.size]
        above = [c for c in nearby if c.baseline <= y + 0.10 * c.size
                 and c.cy < y - 0.12 * c.size]
        below = [c for c in nearby if c.baseline > y + 0.28 * c.size
                 and c.cy > y + 0.08 * c.size]
        if not above or not below:
            continue
        upper_y = max(c.baseline for c in above)
        lower_y = min(c.baseline for c in below)
        above = [c for c in above if abs(c.baseline - upper_y) < 1.5]
        below = [c for c in below if abs(c.baseline - lower_y) < 1.5]
        size = min(c.size for c in above + below)
        # A table rule or distant pair of lines is not evidence of a fraction.
        if x1 - x0 > 12 * size or lower_y - upper_y > 1.65 * size:
            continue
        if not _math_row(above) or not _math_row(below):
            continue
        ink_width = max(max(c.x1 for c in row) - min(c.x0 for c in row) for row in (above, below))
        if x1 - x0 > ink_width + 0.7 * size:
            continue
        yield (x0, x1, y), sorted(above, key=lambda c: c.x0), sorted(below, key=lambda c: c.x0)


def _render_row(row):
    row = sorted(row, key=lambda c: (c.x0, c.order))
    result = ""
    previous = None
    for char in row:
        if previous and char.x0 - previous.x1 > 0.35 * min(char.size, previous.size):
            if result and not result[-1].isspace() and not char.text.startswith((",", ".", ";", ":", ")", "，", "。", "；", "：", "）")):
                result += " "
        result += char.text
        previous = char
    return result.strip()


def _mixed_number(glyphs, members, x0, y, size, fraction_text):
    """A tightly adjacent integer plus a proper numeric fraction is a mixed number."""
    excluded = {c.order for c in members}
    left = sorted((c for c in glyphs if c.order not in excluded and c.text.strip()
                   and c.x0 < x0 and abs(c.baseline - (y + 0.24 * size)) < 0.30 * size),
                  key=lambda c: c.x0, reverse=True)
    whole = []
    edge = x0
    for char in left:
        if not re.fullmatch(r"[0-9]", char.text) or not -0.25 * size < edge - char.x1 < 0.4 * size:
            break
        whole.insert(0, char)
        edge = char.x0
    if not whole:
        return fraction_text, []
    text = "(" + "".join(c.text for c in whole) + "+" + fraction_text + ")"
    sign = next((c for c in left if c.x0 < edge and c.text in {"-", "−"}
                 and -0.25 * size < edge - c.x1 < 0.25 * size), None)
    if sign:
        whole.insert(0, sign)
        text = sign.text + text
    return text, whole


def _render(glyphs, changed_blocks):
    blocks = {}
    for char in sorted(glyphs, key=lambda c: c.order):
        blocks.setdefault(char.block, []).append(char)
    output = []
    for bi, chars in blocks.items():
        if bi not in changed_blocks:
            lines = {}
            for char in chars:
                lines.setdefault(char.line, []).append(char.text)
            output.append("\n".join("".join(line) for line in lines.values()))
            continue
        rows = []
        for char in sorted(chars, key=lambda c: (c.baseline, c.x0)):
            if not char.text.strip():
                # Keep real spaces, but ignore MuPDF's synthetic gap across baselines.
                if char.text == " " and not any(abs(char.baseline - other.baseline) < 1.5
                                                 for other in chars if other.line == char.line
                                                 and other.text.strip()):
                    continue
            target = next((row for row in rows
                           if abs(row[0].baseline - char.baseline) <= 0.24 * min(row[0].size, char.size)), None)
            if target is None:
                rows.append([char])
            else:
                target.append(char)
        output.append("\n".join(_render_row(row) for row in rows if _render_row(row)))
    return "\n\n".join(output).strip()


def _recover_superscripts(glyphs, changed_blocks, stats, blocked):
    removed = set()
    for exponent in sorted(glyphs, key=lambda c: (c.block, c.x0, c.order)):
        if exponent.order in removed or exponent.order in blocked or not exponent.horizontal or not re.fullmatch(r"[0-9a-zA-Z]", exponent.text):
            continue
        bases = [c for c in glyphs if c.block == exponent.block and c.order not in removed and c.order not in blocked
                 and c.horizontal and c.x0 < exponent.x0 and c.size > exponent.size / 0.82
                 # Legacy math fonts can report a box nearly twice the ink width.
                 # The rightmost preceding origin determines the base, not a
                 # non-overlapping box (which can incorrectly choose 2 in 2x²).
                 and -0.75 * c.size <= exponent.x0 - c.x1 <= 0.3 * c.size
                 and exponent.x0 - c.x0 >= 0.15 * c.size
                 and 0.18 * c.size <= c.baseline - exponent.baseline <= 0.75 * c.size
                 and (re.fullmatch(r"[0-9a-zA-Z)]", c.text) or c.recovered)]
        if not bases:
            continue
        base = max(bases, key=lambda c: c.x0)
        if base.text.isalpha() and any(c.text.isalpha() and c.order != base.order
                                      and c.x0 < base.x0 and -0.1 * base.size <= base.x0 - c.x1 <= 0.12 * base.size
                                      and abs(c.baseline - base.baseline) < 1.5 for c in glyphs):
            continue  # Raised citations after words are not exponentiation.
        group = [exponent]
        for other in sorted(glyphs, key=lambda c: c.x0):
            if other.order == exponent.order or other.order in removed or other.block != exponent.block:
                continue
            if (other.x0 >= group[-1].x1 - 0.1 * exponent.size
                    and other.x0 - group[-1].x1 <= 0.25 * exponent.size
                    and abs(other.baseline - exponent.baseline) < 1
                    and abs(other.size - exponent.size) < 1
                    and re.fullmatch(r"[0-9a-zA-Z+\-]", other.text)):
                group.append(other)
        value = "".join(c.text for c in group)
        base.text += "^" + (value if value.isdigit() or len(value) == 1 else f"({value})")
        base.x1 = max(c.x1 for c in group)
        removed.update(c.order for c in group)
        changed_blocks.add(base.block)
        stats["superscripts_recovered"] += 1
    return [c for c in glyphs if c.order not in removed]


def extract_math_layout(page, normalize_character: Callable[[str, str], str]) -> tuple[str, dict]:
    """Extract text plus recovery counts without modifying the PDF or doing OCR."""
    glyphs = _glyphs(page, normalize_character)
    stats = {"fractions_recovered": 0, "superscripts_recovered": 0, "layout_warnings": []}
    changed_blocks = set()
    consumed = set()
    replacements = []
    candidates = list(_fraction_candidates(glyphs, _bars(page)))
    member_sets = [{c.order for c in top + bottom} for _, top, bottom in candidates]
    complex_candidates = {i for i, ids in enumerate(member_sets)
                          if any(ids & other for j, other in enumerate(member_sets) if i != j)}
    blocked = set()
    for i, ((x0, x1, _), top, bottom) in enumerate(candidates):
        members = top + bottom
        extra = [c for c in glyphs if c.order not in member_sets[i] and c.text.strip()
                 and x0 <= c.cx <= x1
                 and min(m.y0 for m in members) <= c.cy <= max(m.y1 for m in members)]
        if extra:
            complex_candidates.add(i)
            blocked.update(c.order for c in extra)
    for i in complex_candidates:
        blocked.update(member_sets[i])
    if complex_candidates:
        stats["layout_warnings"].append("complex_fraction_layout")
    for candidate_index, ((x0, x1, y), numerator, denominator) in enumerate(candidates):
        if candidate_index in complex_candidates:
            continue
        members = numerator + denominator
        if any(c.order in consumed for c in members):
            continue
        first = min(members, key=lambda c: c.order)
        size = max(c.size for c in members)
        top = "".join(c.text for c in numerator)
        bottom = "".join(c.text for c in denominator)
        fraction_text = f"({top})/({bottom})"
        if top.isascii() and top.isdigit() and bottom.isascii() and bottom.isdigit() and 0 < int(top) < int(bottom):
            fraction_text, whole = _mixed_number(glyphs, members, x0, y, size, fraction_text)
            members += whole
            if whole:
                x0 = min(c.x0 for c in whole)
                first = min(members, key=lambda c: c.order)
        replacements.append(_Glyph(
            fraction_text,
            x0, min(c.y0 for c in members), x1, max(c.y1 for c in members),
            y + 0.24 * size, size, first.block, first.line, first.order, recovered=True,
        ))
        consumed.update(c.order for c in members)
        changed_blocks.update(c.block for c in members)
        stats["fractions_recovered"] += 1
    glyphs = [c for c in glyphs if c.order not in consumed] + replacements
    glyphs = _recover_superscripts(glyphs, changed_blocks, stats, blocked)
    return _render(glyphs, changed_blocks), stats
