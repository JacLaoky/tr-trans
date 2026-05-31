"""
math_solver.py — Detect and solve arithmetic problems from OCR'd Korean game text.

Supported formats
-----------------
  Arabic operators / digits (most common in quiz maps):
      3 + 5 = ?          → 8
      18 ÷ 3 = □         → 6
      4 × ? = 20         → 5
      ? - 3 = 4          → 7
      just "7 + 8"       → 15   (no equals sign, still solved)

  Korean operator words:
      삼 더하기 오 = ?   → 8
      15 나누기 3 = □    → 5

  Mixed / comparison:
      3 × 4 = 12  (O/X)  → detected as True/False problem → "O (맞다)"
      3 + 5 ○ 9           → fill the comparison sign

Returns
-------
  (expression: str, answer: str) or None if no math detected.
"""
import re

# ── Korean number words → digit string ───────────────────────────────────────
_KO_DIGIT: dict[str, str] = {
    '영': '0', '일': '1', '이': '2', '삼': '3', '사': '4',
    '오': '5', '육': '6', '칠': '7', '팔': '8', '구': '9',
}
# Multi-char units (replace before single digits to avoid partial matches)
_KO_MULTIDIGIT: dict[str, str] = {
    '십일': '11', '십이': '12', '십삼': '13', '십사': '14', '십오': '15',
    '십육': '16', '십칠': '17', '십팔': '18', '십구': '19',
    '이십': '20', '삼십': '30', '사십': '40', '오십': '50',
    '육십': '60', '칠십': '70', '팔십': '80', '구십': '90',
    '십': '10', '백': '100',
}

# ── Korean operator words → Python operator symbol ───────────────────────────
_KO_OP: dict[str, str] = {
    '더하기':   '+',
    '플러스':   '+',
    '빼기':     '-',
    '마이너스': '-',
    '곱하기':   '*',
    '곱셈':     '*',
    '나누기':   '/',
    '나눗셈':   '/',
    '제곱':     '**',   # "제곱" = square (rare but present in some maps)
}

# ── Symbols that mean "unknown" ───────────────────────────────────────────────
_UNK_RE  = re.compile(r'[□■○◯＿ㅁ]|(?<!\d)\?(?!\s*$)|_+')
_FRAC_RE = re.compile(r'(\d+)\s*/\s*(\d+)')   # e.g. "6 / 3" – might be division

# ── True/False answer labels ──────────────────────────────────────────────────
_TRUE_LABELS  = ('O', '맞다', '참', 'True', '정답')
_FALSE_LABELS = ('X', '틀리다', '거짓', 'False', '오답')


def _normalise(text: str) -> str:
    """Replace Korean number words and operator names with ASCII equivalents."""
    t = text.replace('\n', ' ').replace('\r', ' ').strip()

    # ── Tales Runner golden game-font OCR misreads ────────────────────────────
    # EasyOCR maps these stylised symbols to specific characters.
    _GAME_FONT = {
        '응': '/',   # ÷ → 응  (Korean model)
        '클': '=',   # = → 클  (Korean model)
        'ㅡ': '-',   # ─ → ㅡ  (minus / long-vowel confusion)
        '곱': '*',   # 곱 sometimes appears for ×
    }
    for wrong, right in _GAME_FONT.items():
        t = t.replace(wrong, right)

    # Period (with optional surrounding spaces) between digit groups → ÷
    # Korean OCR reads ÷ as '.' in some font variants: "712 . 008" or "712.008"
    # Tales Runner operands are always integers, so digit . digit = division.
    t = re.sub(r'(\d)\s*\.\s*(\d)', r'\1/\2', t)

    # Korean multi-char numbers first (십일 before 십)
    for ko, num in sorted(_KO_MULTIDIGIT.items(), key=lambda p: -len(p[0])):
        t = t.replace(ko, num)
    # Single Korean digits
    for ko, dig in sorted(_KO_DIGIT.items(), key=lambda p: -len(p[0])):
        t = t.replace(ko, dig)
    # Korean operator words (longest first to avoid sub-word hits)
    for ko, sym in sorted(_KO_OP.items(), key=lambda p: -len(p[0])):
        t = t.replace(ko, f' {sym} ')

    # Normalise Unicode maths symbols
    t = t.replace('×', '*').replace('÷', '/').replace('÷', '/')
    t = t.replace('−', '-').replace('–', '-').replace('—', '-')
    # OCR often reads "×" as "x" or "X"
    # Only do this if surrounded by digits/spaces to avoid word conflicts
    t = re.sub(r'(?<=\d)\s*[xX]\s*(?=\d)', ' * ', t)

    # Replace unknown-placeholder chars with '?'
    t = _UNK_RE.sub('?', t)

    # Collapse spaces between consecutive digits (OCR sometimes splits "348" → "3 4 8")
    # Apply repeatedly for long sequences like "0 0 4"
    for _ in range(6):
        t2 = re.sub(r'(\d) (\d)', r'\1\2', t)
        if t2 == t:
            break
        t = t2

    # Strip leading zeros so Python eval accepts them: 004 → 4, 0012 → 12
    # (only when preceded by a non-digit and followed by a non-zero digit)
    t = re.sub(r'(?<![.\d])0+(?=[1-9])', '', t)

    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _safe_eval(expr: str):
    """
    Safely evaluate a simple arithmetic expression.
    Returns a number (int or float) or None.
    """
    # Whitelist: only digits, spaces, and basic operators
    if re.search(r'[^0-9\s\+\-\*\/\.\(\)\*]', expr):
        return None
    if len(expr) > 60:
        return None
    try:
        v = eval(expr, {"__builtins__": {}}, {})   # nosec – whitelist checked above
        if not isinstance(v, (int, float)):
            return None
        if isinstance(v, float) and v.is_integer():
            return int(v)
        # Round to 4 decimal places for display cleanliness
        return round(v, 4)
    except Exception:
        return None


def _fmt(v) -> str:
    """Format a numeric answer for display."""
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def _fix_1_7(a_str: str, b_str: str, op: str):
    """
    OCR often confuses '1' and '7' in stylised game fonts.
    For division, Tales Runner always uses clean integer answers.
    If  a / b  is not an integer, try all single-digit 1↔7 swaps in
    both operands until we find a pair that gives an integer quotient.

    Returns (fixed_a_str, fixed_b_str, answer_int) or None.
    Only applies to '/' because +,-,* always give integers anyway.

    Priority: fix the dividend (a) first; fixing the divisor to ≤1 is
    skipped (a÷1 is never a real game puzzle).
    """
    if op != '/':
        return None

    def single_swaps(s: str):
        """Every version of s with exactly one 1↔7 flip (not the original)."""
        for i, c in enumerate(s):
            if c == '1':
                yield s[:i] + '7' + s[i+1:]
            elif c == '7':
                yield s[:i] + '1' + s[i+1:]

    b_int = int(b_str)

    # ── Priority 1: fix only the dividend, keep divisor unchanged ──────────
    for av in single_swaps(a_str):
        q = int(av) / b_int
        if q == int(q) and q > 0:
            return av, b_str, int(q)

    # ── Priority 2: fix only the divisor (skip trivial divisors ≤ 1) ──────
    for bv in single_swaps(b_str):
        bi = int(bv)
        if bi <= 1:          # a÷1 = a is never a meaningful puzzle
            continue
        q = int(a_str) / bi
        if q == int(q) and q > 0:
            return a_str, bv, int(q)

    # ── Priority 3: fix both simultaneously ────────────────────────────────
    for av in single_swaps(a_str):
        for bv in single_swaps(b_str):
            bi = int(bv)
            if bi <= 1:
                continue
            q = int(av) / bi
            if q == int(q) and q > 0:
                return av, bv, int(q)

    return None


def solve(text: str) -> tuple[str, str] | None:
    """
    Detect a math problem in *text* and return (short_expression, answer).
    Returns None if no recognisable math found.

    Examples
    --------
    >>> solve("3 + 5 = ?")
    ('3 + 5 = ?', '8')
    >>> solve("4 × ? = 20")
    ('4 × ? = 20', '5')
    >>> solve("삼 더하기 오")
    ('3 + 5', '8')
    """
    t = _normalise(text)

    # ── Pattern 2/3 FIRST: unknown (?) present → solve for the unknown ─────────
    # (must run before True/False check so "? + 3 = 7" isn't mis-classified)

    # ── Pattern 2:  ?  op  b  =  c  ─────────────────────────────────────────
    m = re.search(
        r'\?\s*([\+\-\*\/])\s*(\d+(?:\.\d+)?)\s*=\s*(\d+(?:\.\d+)?)', t)
    if m:
        oper, b, c = m.group(1), float(m.group(2)), float(m.group(3))
        inv_expr = {
            '+': f'{c} - {b}',
            '-': f'{c} + {b}',
            '*': f'{c} / {b}' if b != 0 else None,
            '/': f'{c} * {b}',
        }.get(oper)
        if inv_expr:
            ans = _safe_eval(inv_expr)
            if ans is not None:
                return (f'? {oper} {b:.4g} = {c:.4g}', _fmt(ans))

    # ── Pattern 3:  a  op  ?  =  c  ─────────────────────────────────────────
    m = re.search(
        r'(\d+(?:\.\d+)?)\s*([\+\-\*\/])\s*\?\s*=\s*(\d+(?:\.\d+)?)', t)
    if m:
        a, oper, c = float(m.group(1)), m.group(2), float(m.group(3))
        try:
            if   oper == '+': ans = c - a
            elif oper == '-': ans = a - c
            elif oper == '*': ans = c / a if a else None
            elif oper == '/': ans = a / c if c else None
            else:             ans = None
        except Exception:
            ans = None
        if ans is not None:
            ans_v = int(ans) if isinstance(ans, float) and ans.is_integer() else round(ans, 4)
            return (f'{a:.4g} {oper} ? = {c:.4g}', _fmt(ans_v))

    # ── True/False check  "3 × 4 = 12"  ─────────────────────────────────────
    # Only when there is NO unknown (?) in the text
    if '?' not in t:
        ov_match = re.search(
            r'([\d\s\+\-\*\/\.\(\)\*]+)\s*=\s*([\d\.]+)\s*$', t)
        if ov_match:
            lhs_str = ov_match.group(1).strip()
            rhs_str = ov_match.group(2).strip()
            lhs_val = _safe_eval(lhs_str)
            rhs_val = _safe_eval(rhs_str)
            if lhs_val is not None and rhs_val is not None:
                correct = abs(lhs_val - rhs_val) < 1e-9
                label = "O ✓ 맞다" if correct else "X ✗ 틀리다"
                return (f"{lhs_str} = {rhs_str}", label)

    # ── Pattern 1:  <expr> = ?  or  <expr> =  ────────────────────────────────
    m = re.search(r'([\d\s\+\-\*\/\.\(\)\*]+)\s*=\s*\??$', t)
    if m:
        lhs = m.group(1).strip()
        ans = _safe_eval(lhs)
        if ans is not None:
            # For division: answer must be a positive integer (game design).
            # If it isn't, OCR likely swapped 1 ↔ 7 — try all single swaps.
            div_m = re.fullmatch(r'(\d+)\s*/\s*(\d+)', lhs.strip())
            if div_m and (not isinstance(ans, int) or ans <= 0):
                fix = _fix_1_7(div_m.group(1), div_m.group(2), '/')
                if fix:
                    fa, fb, fq = fix
                    return (f'{fa} / {fb} = ?', str(fq))
            return (lhs + ' = ?', _fmt(ans))

    # ── Pattern 4:  bare expression  "3 + 5"  ────────────────────────────────
    m = re.search(r'(\d+(?:\.\d+)?)\s*([\+\-\*\/\*]{1,2})\s*(\d+(?:\.\d+)?)', t)
    if m:
        ans = _safe_eval(m.group(0))
        if ans is not None:
            return (m.group(0).strip(), _fmt(ans))

    return None


def solve_alternatives(text: str) -> list[tuple[str, str]]:
    """
    Like solve(), but when the operator is - or /, also return the other
    interpretation so the user can pick the right one by looking at the track.

    Returns list of (display_expression, answer_str):
      • always [primary]  for + and ×
      • [sub_result, div_result]  when both make sense
      • [primary]  if the alternative is not a clean integer
    """
    import re as _re

    primary = solve(text)
    if not primary:
        return []

    expr, ans = primary

    # Extract  a OP b  from the solved expression
    m = _re.search(r'(\d+)\s*([-/])\s*(\d+)', expr)
    if not m:
        return [primary]

    a, op, b_s = int(m.group(1)), m.group(2), int(m.group(3))
    if b_s == 0:
        return [primary]

    if op == '-':
        # Primary is subtraction → also show division (if integer)
        div_v = a / b_s
        if div_v == int(div_v) and div_v > 0:
            return [
                (f'{a} − {b_s}',  ans),
                (f'{a} ÷ {b_s}',  str(int(div_v))),
            ]

    elif op == '/':
        # Primary is division → also show subtraction
        sub_v = a - b_s
        return [
            (f'{a} ÷ {b_s}',  ans),
            (f'{a} − {b_s}',  str(sub_v)),
        ]

    return [primary]


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        "3 + 5 = ?",
        "18 ÷ 3 = □",
        "4 × ? = 20",
        "? + 3 = 7",
        "삼 더하기 오",
        "15 나누기 3 = ?",
        "7 × 8",
        "3 × 4 = 12",    # True/False
        "3 × 4 = 13",    # True/False (wrong)
        "이십 - 팔 = ?",
        "just some random Korean text 안녕하세요",
    ]
    for t in tests:
        r = solve(t)
        print(f"  {t!r:35s} → {r}")
