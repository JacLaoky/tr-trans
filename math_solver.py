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

    # '=' in the MIDDLE of the expression is likely a misread '-'
    # e.g. OCR gives "567 = 009 = ?" → should be "567 - 009 = ?"
    # Keep the final '=' (the one before '?' or at end of string).
    t = re.sub(r'=(?!\s*\??$)', '-', t)

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


def _div_fmt(v: float) -> str:
    return str(int(v)) if v == int(v) else f'{v:.1f}'


def _first_17_swap(a_s: str, b_s: str) -> tuple[str, str, bool]:
    """Return (new_a_s, new_b_s, changed) after the first single 1↔7 flip."""
    for i, c in enumerate(a_s):
        if c in '17':
            return a_s[:i] + ('7' if c == '1' else '1') + a_s[i+1:], b_s, True
    for i, c in enumerate(b_s):
        if c in '17':
            return a_s, b_s[:i] + ('7' if c == '1' else '1') + b_s[i+1:], True
    return a_s, b_s, False


def _best_17_swap_for_div(a_s: str, b_s: str) -> tuple[str, str, bool]:
    """Return the single 1↔7 swap that makes a÷b an integer (÷-heuristic)."""
    b = int(b_s)
    for i, c in enumerate(a_s):
        if c in '17':
            na = a_s[:i] + ('7' if c == '1' else '1') + a_s[i+1:]
            q = int(na) / b
            if q == int(q) and q > 0:
                return na, b_s, True
    a = int(a_s)
    for i, c in enumerate(b_s):
        if c in '17':
            nb = b_s[:i] + ('7' if c == '1' else '1') + b_s[i+1:]
            bi = int(nb)
            if bi > 1 and a / bi == int(a / bi) and a / bi > 0:
                return a_s, nb, True
    return a_s, b_s, False


def solve_alternatives(text: str) -> list[tuple[str, str]]:
    """
    Return 1 / 2 / 4 answer candidates.

    +  ×  (no 1/7 digit in operands)   → 1 column
    +  ×  (has 1/7)                    → 2 columns: orig | 1↔7-swapped
    -  ÷  (no 1/7 or no int-div swap)  → 2 columns: op1  | op2
    -  ÷  (1↔7 swap makes ÷ integer)   → 4 columns: op1_orig | op1_swap | op2_orig | op2_swap
    """
    import re as _re

    primary = solve(text)
    if not primary:
        return []

    expr, ans = primary
    m = _re.search(r'(\d+)\s*([-/+*])\s*(\d+)', expr)
    if not m:
        return [primary]

    a_s, op, b_s = m.group(1), m.group(2), m.group(3)
    a, b = int(a_s), int(b_s)

    # ── Addition / Multiplication: show 1↔7 swap column when present ─────────
    if op in ('+', '*'):
        sym = '+' if op == '+' else '×'
        a2_s, b2_s, found = _first_17_swap(a_s, b_s)
        if not found or (int(a2_s) == a and int(b2_s) == b):
            return [primary]
        a2, b2 = int(a2_s), int(b2_s)
        ans2 = str(a2 + b2) if op == '+' else str(a2 * b2)
        if ans2 == ans:          # swap gives same answer → no need for 2nd col
            return [primary]
        return [
            (f'{a} {sym} {b}',   ans),
            (f'{a2} {sym} {b2}', ans2),
        ]

    # ── Subtraction / Division ────────────────────────────────────────────────
    if b == 0:
        return [primary]

    # Only promote to 4 columns when a 1↔7 swap makes ÷ an integer
    # (strongest signal that OCR misread a digit).
    # For the '-' case the original may already give integer ÷; only swap if
    # the swapped version gives a DIFFERENT integer result.
    a2_s, b2_s, found = _best_17_swap_for_div(a_s, b_s)
    a2, b2 = int(a2_s), int(b2_s)

    sub1 = str(a  - b)
    sub2 = str(a2 - b2)
    div1 = _div_fmt(a  / b)
    div2 = _div_fmt(a2 / b2) if b2 != 0 else '?'

    if found and (a2 != a or b2 != b):
        # 4 columns
        if op == '-':
            return [(f'{a} − {b}',   sub1), (f'{a2} − {b2}', sub2),
                    (f'{a} ÷ {b}',   div1), (f'{a2} ÷ {b2}', div2)]
        else:
            # Use div1 (not ans) so format is consistent with _div_fmt
            return [(f'{a} ÷ {b}',   div1), (f'{a2} ÷ {b2}', div2),
                    (f'{a} − {b}',   sub1), (f'{a2} − {b2}', sub2)]
    else:
        # 2 columns
        if op == '-':
            return [(f'{a} − {b}', sub1), (f'{a} ÷ {b}', div1)]
        else:
            return [(f'{a} ÷ {b}', div1), (f'{a} − {b}', sub1)]


def solve_merged_digits(digits: str) -> list[tuple[str, str]]:
    """
    Called when Tesseract returns only digits (operator invisible/merged).
    Finds the most central valid split and returns all 4 operator results
    so the user can pick the correct one from the track.

    e.g. '030006'  → [×180, ÷5,  +36,  −24]   (30 op 6)
         '5644340' → [×191760, +904, −224]      (564 op 340, ÷ not integer)
    """
    n = len(digits)
    if n < 2:
        return []
    mid = n // 2

    def _ok(left: str, right: str):
        a = int(left.lstrip('0') or '0')
        b = int(right.lstrip('0') or '0')
        return (a, b) if 0 < a <= 999 and 0 < b <= 999 else None

    def _build(a: int, b: int) -> list[tuple[str, str]]:
        # Tesseract reads '-' correctly so subtraction is handled normally.
        # Only show the operators that are invisible to Tesseract: × ÷ +
        results = [(f'{a} × {b}', str(a * b))]
        if b != 0 and a % b == 0:
            results.append((f'{a} ÷ {b}', str(a // b)))
        results.append((f'{a} + {b}', str(a + b)))
        return results

    # Phase 1: simple split near centre
    for i in sorted(range(1, n), key=lambda x: abs(x - mid)):
        pair = _ok(digits[:i], digits[i:])
        if pair:
            return _build(*pair)

    # Phase 2: remove one spurious digit (operator misread as digit)
    for rm in sorted(range(1, n - 1), key=lambda x: abs(x - mid)):
        pair = _ok(digits[:rm], digits[rm + 1:])
        if pair:
            return _build(*pair)

    return []


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
