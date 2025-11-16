import re
from typing import Optional, Dict, Any


def parse_money(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    # accepts "$ 102,794", "$102,794.00", "102,794"
    s = str(s)
    m = re.search(r"[-+]?\$?\s*([0-9,]+(?:\.[0-9]+)?)", s.replace(",", ""))
    if not m:
        try:
            return float(s)
        except Exception:
            return None
    try:
        return float(m.group(1))
    except Exception:
        return None

def parse_percent(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    s = str(s)
    m = re.search(r"([-+]?[0-9]+(?:\.[0-9]+)?)\s*%?", s)
    if not m:
        return None
    try:
        return float(m.group(1)) / 100.0
    except Exception:
        return None

def safe_get_by_substring(d: Dict[str, Any], substrings):
    """
    Return first matching numeric-like value in dict keys where key contains any substring.
    """
    for k, v in d.items():
        kl = k.lower()
        for s in substrings:
            if s.lower() in kl:
                return v
    return None