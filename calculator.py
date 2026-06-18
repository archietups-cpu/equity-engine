"""
Equity scoring engine.
Data convention: all series are lists of 5 values, index 0 = most recent year.
Values in millions USD unless stated. Margins/ratios are in % (e.g. 20.0 for 20%).
"""

import math
from typing import Optional, List, Tuple


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe(v):
    """Return v if it's a finite number, else None."""
    if v is None:
        return None
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _div(a, b, default=None):
    if b is None or b == 0 or a is None:
        return default
    return a / b


def _pop_sd(values: list) -> Optional[float]:
    """Population standard deviation of a list, skipping None."""
    clean = [v for v in values if v is not None]
    n = len(clean)
    if n < 2:
        return None
    mean = sum(clean) / n
    return math.sqrt(sum((x - mean) ** 2 for x in clean) / n)


def _drawdown(values: list) -> Optional[float]:
    """(peak - min_after_peak) / peak * 100, skipping None."""
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return None
    peak_val = max(clean)
    peak_idx = clean.index(peak_val)
    after = clean[peak_idx + 1:]
    if not after:
        return 0.0
    trough = min(after)
    if peak_val == 0:
        return None
    return (peak_val - trough) / peak_val * 100


def _clamp(x, lo=1.0, hi=10.0):
    if x is None:
        return None
    return max(lo, min(hi, x))


def _g(series, i):
    """Safe series index — returns None if out of range or series is empty."""
    if not series or i >= len(series):
        return None
    return series[i]


def _pct(a, b):
    """Return a/b * 100 or None."""
    r = _div(a, b)
    return r * 100 if r is not None else None


def _try_component(fn, d):
    """Call fn(d); on any exception return a null-score stub with the error message."""
    try:
        return fn(d)
    except Exception as exc:
        return {"score": None, "subs": {}, "error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Score lookup tables (value → 1-10 score)
# ---------------------------------------------------------------------------

def _score(value, table, ascending=True):
    """
    table: list of (threshold, score), sorted ascending by threshold.
    ascending=True: higher value → higher score (breaks at first threshold exceeded).
    ascending=False: lower value → higher score.
    Returns None if value is None.
    """
    if value is None:
        return None
    for threshold, score in table:
        if ascending:
            if value < threshold:
                return score
        else:
            if value >= threshold:
                return score
    return table[-1][1]


# -- NET DEBT / EBITDA --
_ND_EBITDA = [
    (0, 10), (1, 9), (2, 8), (3, 7), (4, 6),
    (5, 5), (6, 4), (7, 3), (8, 2), (float("inf"), 1),
]


def score_net_debt_ebitda(ratio):
    if ratio is None:
        return None
    if ratio <= 0:
        return 10
    return _score(ratio, [(1, 9), (2, 8), (3, 7), (4, 6), (5, 5), (6, 4), (7, 3), (8, 2)], ascending=True) or 1


# -- DEBT TREND --
def score_debt_trend(delta):
    if delta is None:
        return None
    if delta < -2:     return 10
    if delta < -1.5:   return 9
    if delta < -1:     return 8
    if delta < -0.5:   return 7
    if delta < 0.5:    return 6
    if delta < 1:      return 5
    if delta < 1.5:    return 4
    if delta < 2:      return 3
    if delta < 3:      return 2
    return 1


# -- EARNINGS DURABILITY (EBITDA drawdown %) --
def score_earnings_durability(pct):
    if pct is None:
        return None
    if pct < 10:   return 10
    if pct < 15:   return 9
    if pct < 20:   return 8
    if pct < 25:   return 7
    if pct < 35:   return 6
    if pct < 45:   return 5
    if pct < 55:   return 4
    if pct < 65:   return 3
    if pct < 80:   return 2
    return 1


# -- INTEREST COVERAGE LEVEL (EBIT/Interest) --
def score_coverage_level(ratio):
    if ratio is None:
        return None
    if ratio > 15:   return 10
    if ratio > 12:   return 9
    if ratio > 10:   return 8
    if ratio > 8:    return 7
    if ratio > 6:    return 6
    if ratio > 5:    return 5
    if ratio > 4:    return 4
    if ratio > 3:    return 3
    if ratio > 2:    return 2
    return 1


# -- INTEREST COVERAGE TREND (ratio of ratios) --
def score_coverage_trend(ratio):
    if ratio is None:
        return None
    if ratio > 1.2:    return 10
    if ratio > 1.05:   return 8
    if ratio > 0.95:   return 7
    if ratio > 0.8:    return 6
    if ratio > 0.65:   return 5
    if ratio > 0.5:    return 4
    if ratio > 0.35:   return 3
    if ratio > 0.2:    return 2
    return 1


# -- EARNINGS BUFFER VS INTEREST ((EBIT - Interest)/EBIT * 100) --
def score_earnings_buffer(pct):
    if pct is None:
        return None
    if pct > 90:   return 10
    if pct > 80:   return 9
    if pct > 70:   return 8
    if pct > 60:   return 7
    if pct > 50:   return 6
    if pct > 40:   return 5
    if pct > 30:   return 4
    if pct > 20:   return 3
    if pct > 10:   return 2
    return 1


# -- FCF/EBIT CONVERSION % --
def score_fcf_ebit(pct):
    if pct is None:
        return None
    # > 150 % is anomalously high: D&A almost certainly far exceeds capex,
    # which inflates OCF relative to EBIT. Must be checked BEFORE the ideal
    # band so that 200 % (the cap) scores 7 rather than 10.
    if pct > 150:  return 7
    if pct > 120:  return 10
    if pct > 100:  return 9
    if pct > 90:   return 8
    if pct > 80:   return 7
    if pct > 70:   return 6
    if pct > 60:   return 5
    if pct > 50:   return 4
    if pct > 40:   return 3
    if pct > 20:   return 2
    return 1


# -- FCF STABILITY / DRAWDOWN % (used in both FR and CG) --
def score_fcf_drawdown(pct):
    if pct is None:
        return None
    if pct < 10:   return 10
    if pct < 15:   return 9
    if pct < 20:   return 8
    if pct < 25:   return 7
    if pct < 35:   return 6
    if pct < 45:   return 5
    if pct < 55:   return 4
    if pct < 65:   return 3
    if pct < 80:   return 2
    return 1


# -- FCF TREND % change --
def score_fcf_trend(pct):
    if pct is None:
        return None
    if pct > 100:  return 10
    if pct > 70:   return 9
    if pct > 50:   return 8
    if pct > 30:   return 7
    if pct > -10:  return 6
    if pct > -30:  return 5
    if pct > -50:  return 4
    if pct > -70:  return 3
    if pct > -90:  return 2
    return 1


# -- EBITDA MARGIN STABILITY SD (pp) --
def score_ebitda_margin_sd_fr(sd):
    if sd is None:
        return None
    if sd < 1:    return 10
    if sd < 2:    return 9
    if sd < 3:    return 8
    if sd < 4:    return 7
    if sd < 5:    return 6
    if sd < 6:    return 5
    if sd < 8:    return 4
    if sd < 10:   return 3
    if sd < 15:   return 2
    return 1


# -- REVENUE STABILITY DRAWDOWN % (used in Financial Risk earnings stability) --
def score_rev_stability_drawdown(pct):
    if pct is None:
        return None
    if pct < 5:    return 10
    if pct < 10:   return 9
    if pct < 15:   return 8
    if pct < 20:   return 7
    if pct < 30:   return 6
    if pct < 40:   return 5
    if pct < 50:   return 4
    if pct < 60:   return 3
    if pct < 70:   return 2
    return 1


# -- EQUITY RATIO (equity/assets %) --
def score_equity_ratio(pct):
    if pct is None:
        return None
    if pct > 60:   return 10
    if pct > 50:   return 9
    if pct > 40:   return 8
    if pct > 35:   return 7
    if pct > 30:   return 6
    if pct > 25:   return 5
    if pct > 20:   return 4
    if pct > 15:   return 3
    if pct > 10:   return 2
    return 1


# -- NET DEBT TO EQUITY --
def score_nd_equity(ratio):
    if ratio is None:
        return None
    if ratio < 0.1:    return 10
    if ratio < 0.25:   return 9
    if ratio < 0.5:    return 8
    if ratio < 0.75:   return 7
    if ratio < 1.0:    return 6
    if ratio < 1.25:   return 5
    if ratio < 1.5:    return 4
    if ratio < 2.0:    return 3
    if ratio < 3.0:    return 2
    return 1


# -- ASSET COVERAGE (total assets / total debt) --
def score_asset_coverage(ratio):
    if ratio is None:
        return None
    if ratio > 5:      return 10
    if ratio > 4:      return 9
    if ratio > 3:      return 8
    if ratio > 2.5:    return 7
    if ratio > 2.0:    return 6
    if ratio > 1.75:   return 5
    if ratio > 1.5:    return 4
    if ratio > 1.25:   return 3
    if ratio > 1.1:    return 2
    return 1


# -- OCF / EBIT % --
def score_ocf_ebit(pct):
    if pct is None:
        return None
    # > 150 % is anomalously high: D&A likely inflating OCF vs EBIT.
    # Must be checked BEFORE the ideal band so that 200 % scores 7 not 10.
    if pct > 150:  return 7
    if pct > 140:  return 10
    if pct > 120:  return 9
    if pct > 100:  return 8
    if pct > 90:   return 7
    if pct > 80:   return 6
    if pct > 70:   return 5
    if pct > 60:   return 4
    if pct > 50:   return 3
    if pct > 30:   return 2
    return 1


# -- WORKING CAPITAL DRAG % --
def score_wc_drag(pct):
    if pct is None:
        return None
    if pct < -5:   return 10
    if pct < 0:    return 9
    if pct < 2:    return 8
    if pct < 4:    return 7
    if pct < 6:    return 6
    if pct < 8:    return 5
    if pct < 10:   return 4
    if pct < 12:   return 3
    if pct < 15:   return 2
    return 1


# -- AVERAGE FCF MARGIN % --
def score_avg_fcf_margin(pct):
    if pct is None:
        return None
    if pct > 25:   return 10
    if pct > 20:   return 9
    if pct > 15:   return 8
    if pct > 12:   return 7
    if pct > 10:   return 6
    if pct > 7:    return 5
    if pct > 5:    return 4
    if pct > 3:    return 3
    if pct > 1:    return 2
    return 1


# -- FCF MARGIN STABILITY SD % --
def score_fcf_margin_sd(sd):
    if sd is None:
        return None
    if sd < 2:    return 10
    if sd < 3:    return 9
    if sd < 4:    return 8
    if sd < 5:    return 7
    if sd < 6:    return 6
    if sd < 8:    return 5
    if sd < 10:   return 4
    if sd < 12:   return 3
    if sd < 15:   return 2
    return 1


# -- FCF MARGIN TREND pp --
def score_fcf_margin_trend(pp):
    if pp is None:
        return None
    if pp > 10:   return 10
    if pp > 7:    return 9
    if pp > 5:    return 8
    if pp > 3:    return 7
    if pp > 0:    return 6
    if pp > -2:   return 5
    if pp > -4:   return 4
    if pp > -6:   return 3
    if pp > -10:  return 2
    return 1


# -- POSITIVE FCF CONSISTENCY (count of years with FCF > 0) --
def score_positive_fcf_count(n):
    if n is None:
        return None
    if n >= 5:  return 10
    if n >= 4:  return 8
    if n >= 3:  return 6
    if n >= 2:  return 4
    if n >= 1:  return 2
    return 1


# -- AVERAGE EBITDA MARGIN % --
def score_avg_ebitda_margin(pct):
    if pct is None:
        return None
    if pct > 35:   return 10
    if pct > 30:   return 9
    if pct > 25:   return 8
    if pct > 20:   return 7
    if pct > 15:   return 6
    if pct > 12:   return 5
    if pct > 9:    return 4
    if pct > 6:    return 3
    if pct > 3:    return 2
    return 1


# -- AVERAGE EBIT MARGIN % --
def score_avg_ebit_margin(pct):
    if pct is None:
        return None
    if pct > 25:   return 10
    if pct > 20:   return 9
    if pct > 16:   return 8
    if pct > 12:   return 7
    if pct > 9:    return 6
    if pct > 6:    return 5
    if pct > 4:    return 4
    if pct > 2:    return 3
    if pct > 0:    return 2
    return 1


# -- MARGIN TREND BQ pp change in EBITDA margin --
def score_margin_trend_bq(pp):
    if pp is None:
        return None
    if pp > 5:    return 10
    if pp > 3:    return 9
    if pp > 1:    return 8
    if pp > 0:    return 7
    if pp > -1:   return 6
    if pp > -2:   return 5
    if pp > -4:   return 4
    if pp > -6:   return 3
    if pp > -8:   return 2
    return 1


# -- EBITDA MARGIN VOLATILITY SD pp (BQ, tighter thresholds) --
def score_ebitda_margin_vol_bq(sd):
    if sd is None:
        return None
    if sd < 0.3:   return 10
    if sd < 0.6:   return 9
    if sd < 1.0:   return 8
    if sd < 1.5:   return 7
    if sd < 2.0:   return 6
    if sd < 4.0:   return 5
    if sd < 6.0:   return 4
    if sd < 8.0:   return 3
    if sd < 12.0:  return 2
    return 1


# -- EBIT MARGIN VOLATILITY SD pp --
def score_ebit_margin_vol_bq(sd):
    if sd is None:
        return None
    if sd < 0.6:   return 10
    if sd < 1.0:   return 9
    if sd < 1.5:   return 8
    if sd < 2.0:   return 7
    if sd < 3.0:   return 6
    if sd < 4.0:   return 5
    if sd < 5.0:   return 4
    if sd < 7.0:   return 3
    if sd < 10.0:  return 2
    return 1


# -- REVENUE DRAWDOWN BQ % (tighter thresholds than FR) --
def score_rev_drawdown_bq(pct):
    if pct is None:
        return None
    if pct < 2:    return 10
    if pct < 4:    return 9
    if pct < 6:    return 8
    if pct < 10:   return 7
    if pct < 15:   return 6
    if pct < 25:   return 5
    if pct < 35:   return 4
    if pct < 45:   return 3
    if pct < 60:   return 2
    return 1


# -- REVENUE VOLATILITY CV % --
def score_rev_volatility(cv):
    if cv is None:
        return None
    if cv < 1.5:   return 10
    if cv < 2.5:   return 9
    if cv < 4.0:   return 8
    if cv < 6.0:   return 7
    if cv < 9.0:   return 6
    if cv < 12.0:  return 5
    if cv < 15.0:  return 4
    if cv < 20.0:  return 3
    if cv < 35.0:  return 2
    return 1


# -- REVENUE CAGR % --
def score_revenue_cagr(pct):
    if pct is None:
        return None
    if pct > 12:   return 10
    if pct > 10:   return 9
    if pct > 8:    return 8
    if pct > 6:    return 7
    if pct > 4:    return 6
    if pct > 2:    return 5
    if pct > 0:    return 4
    if pct > -2:   return 3
    if pct > -5:   return 2
    return 1


# -- GROWTH VOLATILITY SD % --
def score_growth_volatility(sd):
    if sd is None:
        return None
    if sd < 2:    return 10
    if sd < 3:    return 9
    if sd < 4:    return 8
    if sd < 6:    return 7
    if sd < 8:    return 6
    if sd < 10:   return 5
    if sd < 13:   return 4
    if sd < 16:   return 3
    if sd < 20:   return 2
    return 1


# -- DOWNSIDE SEVERITY (worst growth %) --
def score_downside_severity(worst):
    if worst is None:
        return None
    if worst > 1:    return 10
    if worst > -1:   return 9
    if worst > -3:   return 8
    if worst > -5:   return 7
    if worst > -10:  return 6
    if worst > -15:  return 5
    if worst > -20:  return 4
    if worst > -30:  return 3
    if worst > -50:  return 2
    return 1


# -- NEGATIVE YEAR COUNT (n growth years < 0) --
def score_negative_years(n):
    if n is None:
        return None
    if n == 0:   return 10
    if n == 1:   return 8
    if n == 2:   return 6
    if n == 3:   return 3
    return 1


# -- GROWTH DIRECTION CONSISTENCY (years with growth >= 2%) --
def score_growth_direction(n):
    if n is None:
        return None
    if n >= 4:   return 10
    if n >= 3:   return 8
    if n >= 2:   return 6
    if n >= 1:   return 4
    return 2


# -- MARGIN TREND (GQ) pp change in EBITDA margin --
def score_margin_trend_gq(pp):
    if pp is None:
        return None
    if pp > 6:    return 10
    if pp > 4:    return 9
    if pp > 2:    return 8
    if pp > 1:    return 7
    if pp > 0:    return 6
    if pp > -1:   return 5
    if pp > -2:   return 4
    if pp > -4:   return 3
    if pp > -6:   return 2
    return 1


# -- GROWTH VS MARGIN ALIGNMENT lookup --
def score_growth_margin_alignment(rev_cagr, margin_trend_pp):
    if rev_cagr is None or margin_trend_pp is None:
        return None
    rev = "positive" if rev_cagr > 0.5 else ("negative" if rev_cagr < -0.5 else "flat")
    mar = "positive" if margin_trend_pp > 0.5 else ("negative" if margin_trend_pp < -0.5 else "flat")
    table = {
        ("positive", "positive"): 10,
        ("positive", "flat"): 8,
        ("positive", "negative"): 3,
        ("flat", "positive"): 7,
        ("flat", "flat"): 5,
        ("flat", "negative"): 3,
        ("negative", "positive"): 6,
        ("negative", "flat"): 2,
        ("negative", "negative"): 1,
    }
    return table.get((rev, mar), 5)


# -- GROWTH-CASH GAP (revenue CAGR - FCF CAGR) % --
def score_growth_cash_gap(gap):
    if gap is None:
        return None
    if gap < -5:    return 10
    if gap < 0:     return 9
    if gap < 3:     return 7
    if gap < 6:     return 6
    if gap < 10:    return 4
    if gap < 15:    return 3
    if gap < 20:    return 2
    return 1


# -- ALIGNMENT CONSISTENCY (years both rev and FCF growth >= 0) --
def score_alignment_consistency(n):
    if n is None:
        return None
    if n >= 4:   return 10
    if n >= 3:   return 8
    if n >= 2:   return 6
    if n >= 1:   return 4
    return 1


# -- AVERAGE CAPEX INTENSITY % --
def score_avg_capex_intensity(pct):
    if pct is None:
        return None
    if pct < 3:    return 10
    if pct < 5:    return 9
    if pct < 7:    return 8
    if pct < 10:   return 7
    if pct < 13:   return 6
    if pct < 16:   return 5
    if pct < 20:   return 4
    if pct < 25:   return 3
    if pct < 30:   return 2
    return 1


# -- CAPEX INTENSITY STABILITY SD pp --
def score_capex_intensity_sd(sd):
    if sd is None:
        return None
    if sd < 1:    return 10
    if sd < 2:    return 9
    if sd < 3:    return 8
    if sd < 4:    return 7
    if sd < 5:    return 6
    if sd < 7:    return 5
    if sd < 10:   return 4
    if sd < 13:   return 3
    if sd < 16:   return 2
    return 1


# -- CAPEX INTENSITY TREND pp --
def score_capex_intensity_trend(pp):
    if pp is None:
        return None
    if pp < -6:   return 10
    if pp < -4:   return 9
    if pp < -2:   return 8
    if pp < -1:   return 7
    if pp < 0:    return 6
    if pp < 1:    return 5
    if pp < 2:    return 4
    if pp < 4:    return 3
    if pp < 6:    return 2
    return 1


# -- AVERAGE CAPEX / DEPRECIATION RATIO --
def score_avg_capex_depr(ratio):
    if ratio is None:
        return None
    if 0.9 <= ratio <= 1.3:    return 10
    if 0.7 <= ratio < 0.9:     return 8
    if 1.3 < ratio <= 1.7:     return 8
    if 0.5 <= ratio < 0.7:     return 6
    if 1.7 < ratio <= 2.2:     return 6
    if 0.3 <= ratio < 0.5:     return 4
    if 2.2 < ratio <= 3.0:     return 4
    if 0.2 <= ratio < 0.3:     return 2
    if 3.0 < ratio <= 4.0:     return 2
    return 1  # < 0.2 or > 4.0


# -- CAPEX / DEPRECIATION STABILITY SD --
def score_capex_depr_sd(sd):
    if sd is None:
        return None
    if sd < 0.2:   return 10
    if sd < 0.4:   return 9
    if sd < 0.6:   return 8
    if sd < 0.8:   return 7
    if sd < 1.0:   return 6
    if sd < 1.5:   return 5
    if sd < 2.0:   return 4
    if sd < 2.5:   return 3
    if sd < 3.5:   return 2
    return 1


# -- CAPEX / DEPRECIATION TREND (delta ratio) --
def score_capex_depr_trend(delta):
    if delta is None:
        return None
    if -0.5 <= delta <= 0.2:   return 10
    if -1.0 <= delta < -0.5:   return 9
    if 0.2 < delta <= 0.5:     return 8
    if -1.5 <= delta < -1.0:   return 7
    if 0.5 < delta <= 1.0:     return 6
    if -2.0 <= delta < -1.5:   return 5
    if 1.0 < delta <= 1.5:     return 4
    if 1.5 < delta <= 2.0:     return 3
    if 2.0 < delta <= 3.0:     return 2
    if delta > 3.0:            return 1
    return 2  # very negative delta (delta < -2.0)


# -- AVERAGE ROCE % --
def score_avg_roce(pct):
    if pct is None:
        return None
    if pct > 25:   return 10
    if pct > 20:   return 9
    if pct > 16:   return 8
    if pct > 13:   return 7
    if pct > 10:   return 6
    if pct > 7:    return 5
    if pct > 5:    return 4
    if pct > 3:    return 3
    if pct > 0:    return 2
    return 1


# -- ROCE STABILITY SD pp --
def score_roce_sd(sd):
    if sd is None:
        return None
    if sd < 2:    return 10
    if sd < 4:    return 9
    if sd < 6:    return 8
    if sd < 8:    return 7
    if sd < 10:   return 6
    if sd < 13:   return 5
    if sd < 16:   return 4
    if sd < 20:   return 3
    if sd < 25:   return 2
    return 1


# -- ROCE TREND pp --
def score_roce_trend(pp):
    if pp is None:
        return None
    if pp > 10:   return 10
    if pp > 7:    return 9
    if pp > 5:    return 8
    if pp > 3:    return 7
    if pp > 0:    return 6
    if pp > -2:   return 5
    if pp > -4:   return 4
    if pp > -6:   return 3
    if pp > -10:  return 2
    return 1


# ---------------------------------------------------------------------------
# Weighted average helpers
# ---------------------------------------------------------------------------

def _weighted(pairs: List[Tuple]) -> Optional[float]:
    """pairs = [(score, weight), ...]. Returns weighted avg or None if all None."""
    total_w = 0.0
    total_s = 0.0
    for s, w in pairs:
        if s is not None:
            total_s += s * w
            total_w += w
    if total_w == 0:
        return None
    return total_s / total_w


# ---------------------------------------------------------------------------
# Sub-pillar calculators
# ---------------------------------------------------------------------------

def calc_leverage(d: dict) -> dict:
    ebitda = d["ebitda"]
    cash = d["cash"]
    debt = d["long_term_debt"]

    debt0, cash0, ebitda0 = _g(debt, 0), _g(cash, 0), _g(ebitda, 0)
    debt3, cash3, ebitda3 = _g(debt, 3), _g(cash, 3), _g(ebitda, 3)

    nd0 = (debt0 - (cash0 or 0)) if debt0 is not None else None
    nd3 = (debt3 - (cash3 or 0)) if debt3 is not None else None

    nd_ebitda_0 = _div(nd0, ebitda0)
    nd_ebitda_3 = _div(nd3, ebitda3) if nd3 is not None else None
    delta_nd = (nd_ebitda_0 - nd_ebitda_3) if (nd_ebitda_0 is not None and nd_ebitda_3 is not None) else None

    s_ratio = score_net_debt_ebitda(nd_ebitda_0)
    s_trend = score_debt_trend(delta_nd)
    ebitda_dd = _drawdown([v for v in ebitda if v is not None])
    s_durability = score_earnings_durability(ebitda_dd)

    score = _weighted([(s_ratio, 0.55), (s_trend, 0.25), (s_durability, 0.20)])
    return {
        "score": score,
        "subs": {
            "Net Debt/EBITDA": {"score": s_ratio, "raw": round(nd_ebitda_0, 2) if nd_ebitda_0 is not None else None, "desc": "Net debt relative to EBITDA"},
            "Debt Trend": {"score": s_trend, "raw": round(delta_nd, 2) if delta_nd is not None else None, "desc": "Change in leverage over 3 years"},
            "Earnings Durability": {"score": s_durability, "raw": round(ebitda_dd, 1) if ebitda_dd is not None else None, "desc": "Max EBITDA drawdown %"},
        },
    }


def calc_interest_coverage(d: dict) -> dict:
    ebit = d["ebit"]
    interest = d["interest_expense"]

    ebit0, int0 = _g(ebit, 0), _g(interest, 0)
    ebit3, int3 = _g(ebit, 3), _g(interest, 3)

    cov_0 = _div(ebit0, int0)
    cov_3 = _div(ebit3, int3)

    s_level = score_coverage_level(cov_0)
    s_trend = score_coverage_trend(_div(cov_0, cov_3)) if (cov_0 and cov_3) else None

    if ebit0 is not None and ebit0 <= 0:
        s_buffer = 1
        buffer_val = None
    else:
        buffer_val = _pct((ebit0 or 0) - (int0 or 0), ebit0)
        s_buffer = score_earnings_buffer(buffer_val)

    score = _weighted([(s_level, 0.55), (s_trend, 0.25), (s_buffer, 0.20)])
    return {
        "score": score,
        "subs": {
            "Coverage Level": {"score": s_level, "raw": round(cov_0, 2) if cov_0 is not None else None, "desc": "EBIT / Interest Expense"},
            "Coverage Trend": {"score": s_trend, "raw": round(cov_0 / cov_3, 2) if (cov_0 and cov_3) else None, "desc": "Coverage ratio vs 3 years ago"},
            "Earnings Buffer": {"score": s_buffer, "raw": round(buffer_val, 1) if buffer_val is not None else None, "desc": "% EBIT remaining after interest"},
        },
    }


def _calc_fcf_series(d: dict) -> list:
    """Return FCF series (operating CF - capex), length matches the shortest input series."""
    ocf = d["operating_cf"]
    capex = d["capex"]
    n = min(len(ocf), len(capex))
    return [
        (ocf[i] - capex[i]) if (ocf[i] is not None and capex[i] is not None) else None
        for i in range(n)
    ]


def calc_fcf_consistency(d: dict) -> dict:
    fcf = _calc_fcf_series(d)
    ebit = d["ebit"]

    fcf0, fcf3, ebit0 = _g(fcf, 0), _g(fcf, 3), _g(ebit, 0)

    conv_val = _pct(fcf0, ebit0) if fcf0 is not None else None
    if conv_val is not None:
        conv_val = min(conv_val, 200.0)
    s_conv = score_fcf_ebit(conv_val)

    dd = _drawdown([v for v in fcf if v is not None])
    s_stab = score_fcf_drawdown(dd)

    fcf_trend = _pct(fcf0 - fcf3, abs(fcf3)) if (fcf0 is not None and fcf3 and fcf3 != 0) else None
    s_trend = score_fcf_trend(fcf_trend)

    score = _weighted([(s_conv, 0.50), (s_stab, 0.30), (s_trend, 0.20)])
    return {
        "score": score,
        "subs": {
            "FCF Conversion": {"score": s_conv, "raw": round(conv_val, 1) if conv_val is not None else None, "desc": "FCF as % of EBIT"},
            "FCF Stability": {"score": s_stab, "raw": round(dd, 1) if dd is not None else None, "desc": "FCF drawdown %"},
            "FCF Trend": {"score": s_trend, "raw": round(fcf_trend, 1) if fcf_trend is not None else None, "desc": "FCF % change vs 3 years ago"},
        },
    }


def calc_earnings_stability(d: dict) -> dict:
    rev = d["revenue"]
    ebitda = d["ebitda"]
    n = min(len(rev), len(ebitda))

    margins = [_pct(ebitda[i], rev[i]) for i in range(n)]
    sd_margins = _pop_sd([m for m in margins if m is not None])
    s_margin_stab = score_ebitda_margin_sd_fr(sd_margins)

    rev_dd = _drawdown([v for v in rev if v is not None])
    s_rev_stab = score_rev_stability_drawdown(rev_dd)

    score = _weighted([(s_margin_stab, 0.60), (s_rev_stab, 0.40)])
    return {
        "score": score,
        "subs": {
            "EBITDA Margin Stability": {"score": s_margin_stab, "raw": round(sd_margins, 2) if sd_margins is not None else None, "desc": "SD of EBITDA margins (pp)"},
            "Revenue Stability": {"score": s_rev_stab, "raw": round(rev_dd, 1) if rev_dd is not None else None, "desc": "Revenue drawdown %"},
        },
    }


def calc_equity_buffer(d: dict) -> dict:
    assets = d["total_assets"]
    equity = d["equity"]
    debt = d["long_term_debt"]
    cash = d["cash"]

    eq_ratio = _div(equity[0], assets[0]) * 100 if assets[0] else None
    nd = (debt[0] or 0) - (cash[0] or 0) if debt[0] is not None else None
    nd_equity = _div(nd, equity[0]) if (nd is not None and equity[0] and equity[0] > 0) else None
    asset_cov = _div(assets[0], debt[0]) if debt[0] and debt[0] > 0 else None

    s_eq = score_equity_ratio(eq_ratio)
    s_nd_eq = score_nd_equity(nd_equity)
    s_asset = score_asset_coverage(asset_cov)

    score = _weighted([(s_eq, 0.50), (s_nd_eq, 0.30), (s_asset, 0.20)])
    return {
        "score": score,
        "subs": {
            "Equity Ratio": {"score": s_eq, "raw": round(eq_ratio, 1) if eq_ratio is not None else None, "desc": "Equity as % of assets"},
            "Net Debt/Equity": {"score": s_nd_eq, "raw": round(nd_equity, 2) if nd_equity is not None else None, "desc": "Net debt relative to equity"},
            "Asset Coverage": {"score": s_asset, "raw": round(asset_cov, 2) if asset_cov is not None else None, "desc": "Total assets / Total debt"},
        },
    }


def calc_financial_risk(d: dict) -> dict:
    lev = _try_component(calc_leverage, d)
    cov = _try_component(calc_interest_coverage, d)
    fcf_c = _try_component(calc_fcf_consistency, d)
    earn = _try_component(calc_earnings_stability, d)
    eq = _try_component(calc_equity_buffer, d)

    lev_s = lev["score"]
    cov_s = cov["score"]
    fcf_s = fcf_c["score"]
    earn_s = earn["score"]
    eq_s = eq["score"]

    raw = _weighted([(lev_s, 0.35), (cov_s, 0.20), (fcf_s, 0.20), (earn_s, 0.15), (eq_s, 0.10)])

    penalties = []
    if raw is not None:
        if lev_s is not None and lev_s <= 5:
            raw -= 1; penalties.append("Leverage ≤5 → -1")
        if cov_s is not None and cov_s <= 5:
            raw -= 1; penalties.append("Coverage ≤5 → -1")
        if fcf_s is not None and fcf_s <= 5:
            raw -= 1; penalties.append("FCF ≤5 → -1")
        if earn_s is not None and earn_s <= 4:
            raw -= 1; penalties.append("Earnings Stability ≤4 → -1")
        if eq_s is not None and eq_s <= 4:
            raw -= 1; penalties.append("Equity Buffer ≤4 → -1")
        if (lev_s is not None and lev_s < 5) and (earn_s is not None and earn_s < 5):
            raw -= 1; penalties.append("Leverage<5 + Earnings Stability<5 → -1")

    score = _clamp(raw)
    return {
        "score": score,
        "penalties": penalties,
        "components": {
            "Leverage": {**lev, "weight": "35%"},
            "Interest Coverage": {**cov, "weight": "20%"},
            "FCF Consistency": {**fcf_c, "weight": "20%"},
            "Earnings Stability": {**earn, "weight": "15%"},
            "Equity Buffer": {**eq, "weight": "10%"},
        },
    }


# ---------------------------------------------------------------------------
# Cash Generation
# ---------------------------------------------------------------------------

def calc_cash_conversion(d: dict) -> dict:
    fcf = _calc_fcf_series(d)
    ocf = d["operating_cf"]
    ebit = d["ebit"]
    rev = d["revenue"]
    wc = d["wc_change"]  # Macrotrends: positive = cash released

    _raw_fcf_ebit = _div(fcf[0], ebit[0]) * 100 if (fcf[0] is not None and ebit[0]) else None
    conv_pct = min(_raw_fcf_ebit, 200.0) if _raw_fcf_ebit is not None else None
    s_conv = score_fcf_ebit(conv_pct)

    _raw_ocf_ebit = _div(ocf[0], ebit[0]) * 100 if (ocf[0] is not None and ebit[0]) else None
    ocf_ebit_pct = min(_raw_ocf_ebit, 200.0) if _raw_ocf_ebit is not None else None
    s_ocf = score_ocf_ebit(ocf_ebit_pct)

    print(
        f"[CashDebug] OCF={ocf[0]:.1f}  CapEx={d['capex'][0]:.1f}  FCF={fcf[0]:.1f}"
        f"  FCF/EBIT raw={_raw_fcf_ebit:.1f}% → capped={conv_pct:.1f}% → score={s_conv}"
        f"  |  OCF/EBIT raw={_raw_ocf_ebit:.1f}% → capped={ocf_ebit_pct:.1f}% → score={s_ocf}"
        if (ocf[0] is not None and d['capex'][0] is not None and fcf[0] is not None
            and _raw_fcf_ebit is not None and _raw_ocf_ebit is not None)
        else f"[CashDebug] OCF={ocf[0]}  CapEx={d['capex'][0]}  FCF={fcf[0]}  (some values None)"
    )

    # wc_drag: positive = cash absorbed. Macrotrends wc_change sign is inverted.
    wc_drag = _div(-(wc[0] or 0), rev[0]) * 100 if (wc[0] is not None and rev[0]) else None
    s_wc = score_wc_drag(wc_drag)

    score = _weighted([(s_conv, 0.50), (s_ocf, 0.30), (s_wc, 0.20)])
    return {
        "score": score,
        "subs": {
            "FCF/EBIT Conversion": {"score": s_conv, "raw": round(conv_pct, 1) if conv_pct is not None else None, "desc": "FCF as % of EBIT"},
            "OCF/EBIT": {"score": s_ocf, "raw": round(ocf_ebit_pct, 1) if ocf_ebit_pct is not None else None, "desc": "Operating CF as % of EBIT"},
            "WC Absorption": {"score": s_wc, "raw": round(wc_drag, 1) if wc_drag is not None else None, "desc": "Working capital drag on revenue (%)"},
        },
    }


def calc_fcf_margin_pillar(d: dict) -> dict:
    fcf = _calc_fcf_series(d)
    rev = d["revenue"]
    n = min(len(fcf), len(rev))

    margins = [_pct(fcf[i], rev[i]) for i in range(n)]
    valid_m = [m for m in margins if m is not None]
    avg_margin = sum(valid_m) / len(valid_m) if valid_m else None
    s_avg = score_avg_fcf_margin(avg_margin)

    sd = _pop_sd(valid_m)
    s_sd = score_fcf_margin_sd(sd)

    m0, m3 = _g(margins, 0), _g(margins, 3)
    trend = (m0 - m3) if (m0 is not None and m3 is not None) else None
    s_trend = score_fcf_margin_trend(trend)

    score = _weighted([(s_avg, 0.50), (s_sd, 0.30), (s_trend, 0.20)])
    return {
        "score": score,
        "subs": {
            "Average FCF Margin": {"score": s_avg, "raw": round(avg_margin, 1) if avg_margin is not None else None, "desc": "Average FCF as % of revenue"},
            "FCF Margin Stability": {"score": s_sd, "raw": round(sd, 2) if sd is not None else None, "desc": "SD of FCF margins (pp)"},
            "FCF Margin Trend": {"score": s_trend, "raw": round(trend, 1) if trend is not None else None, "desc": "FCF margin change vs 3 years ago (pp)"},
        },
    }


def calc_fcf_stability_cg(d: dict) -> dict:
    fcf = _calc_fcf_series(d)
    clean = [v for v in fcf if v is not None]
    if not clean:
        return {"score": None, "subs": {}}

    # Drawdown: peak FCF to value in next year
    peak_val = max(clean)
    peak_idx = clean.index(peak_val)
    if peak_idx + 1 < len(clean):
        next_val = clean[peak_idx + 1]
        dd = (peak_val - next_val) / peak_val * 100 if peak_val != 0 else None
    else:
        dd = 0.0
    s_dd = score_fcf_drawdown(dd)

    pos_count = sum(1 for v in fcf if v is not None and v > 0)
    s_pos = score_positive_fcf_count(pos_count)

    score = _weighted([(s_dd, 0.60), (s_pos, 0.40)])
    return {
        "score": score,
        "subs": {
            "FCF Drawdown Risk": {"score": s_dd, "raw": round(dd, 1) if dd is not None else None, "desc": "Drop from peak FCF to next year (%)"},
            "Positive FCF Years": {"score": s_pos, "raw": pos_count, "desc": f"Years with positive FCF out of {len([v for v in fcf if v is not None])}"},
        },
    }


def calc_cash_generation(d: dict) -> dict:
    conv = _try_component(calc_cash_conversion, d)
    fcf_m = _try_component(calc_fcf_margin_pillar, d)
    fcf_s = _try_component(calc_fcf_stability_cg, d)

    conv_s = conv["score"]
    fcf_m_s = fcf_m["score"]
    fcf_s_s = fcf_s["score"]

    raw = _weighted([(conv_s, 0.50), (fcf_m_s, 0.30), (fcf_s_s, 0.20)])

    penalties = []
    if raw is not None:
        if conv_s is not None and conv_s < 5:
            raw -= 1; penalties.append("Cash Conversion <5 → -1")
        if fcf_m_s is not None and fcf_m_s < 4:
            raw -= 1; penalties.append("FCF Margin <4 → -1")
        if fcf_s_s is not None and fcf_s_s < 4:
            raw -= 1; penalties.append("FCF Stability <4 → -1")

    score = _clamp(raw)
    return {
        "score": score,
        "penalties": penalties,
        "components": {
            "Cash Conversion": {**conv, "weight": "50%"},
            "FCF Margin": {**fcf_m, "weight": "30%"},
            "FCF Stability": {**fcf_s, "weight": "20%"},
        },
    }


# ---------------------------------------------------------------------------
# Business Quality
# ---------------------------------------------------------------------------

def calc_margin_strength(d: dict) -> dict:
    rev = d["revenue"]
    ebitda = d["ebitda"]
    ebit = d["ebit"]
    n = min(len(rev), len(ebitda), len(ebit))

    ebitda_margins = [_pct(ebitda[i], rev[i]) for i in range(n)]
    ebit_margins = [_pct(ebit[i], rev[i]) for i in range(n)]

    valid_em = [m for m in ebitda_margins if m is not None]
    valid_bm = [m for m in ebit_margins if m is not None]
    avg_ebitda = sum(valid_em) / len(valid_em) if valid_em else None
    avg_ebit = sum(valid_bm) / len(valid_bm) if valid_bm else None

    s_ebitda = score_avg_ebitda_margin(avg_ebitda)
    s_ebit = score_avg_ebit_margin(avg_ebit)

    em0, em3 = _g(ebitda_margins, 0), _g(ebitda_margins, 3)
    trend = (em0 - em3) if (em0 is not None and em3 is not None) else None
    s_trend = score_margin_trend_bq(trend)

    score = _weighted([(s_ebitda, 0.45), (s_ebit, 0.35), (s_trend, 0.20)])
    return {
        "score": score,
        "avg_ebitda_margin": avg_ebitda,
        "subs": {
            "Avg EBITDA Margin": {"score": s_ebitda, "raw": round(avg_ebitda, 1) if avg_ebitda is not None else None, "desc": "5-year average EBITDA margin (%)"},
            "Avg EBIT Margin": {"score": s_ebit, "raw": round(avg_ebit, 1) if avg_ebit is not None else None, "desc": "5-year average EBIT margin (%)"},
            "Margin Trend": {"score": s_trend, "raw": round(trend, 1) if trend is not None else None, "desc": "EBITDA margin change vs 3 years ago (pp)"},
        },
    }


def calc_margin_stability(d: dict) -> dict:
    rev = d["revenue"]
    ebitda = d["ebitda"]
    ebit = d["ebit"]
    n = min(len(rev), len(ebitda), len(ebit))

    ebitda_margins = [_pct(ebitda[i], rev[i]) for i in range(n)]
    ebit_margins = [_pct(ebit[i], rev[i]) for i in range(n)]

    sd_ebitda = _pop_sd([m for m in ebitda_margins if m is not None])
    sd_ebit = _pop_sd([m for m in ebit_margins if m is not None])

    s_ebitda = score_ebitda_margin_vol_bq(sd_ebitda)
    s_ebit = score_ebit_margin_vol_bq(sd_ebit)

    score = _weighted([(s_ebitda, 0.60), (s_ebit, 0.40)])
    return {
        "score": score,
        "subs": {
            "EBITDA Margin Volatility": {"score": s_ebitda, "raw": round(sd_ebitda, 2) if sd_ebitda is not None else None, "desc": "SD of EBITDA margins (pp)"},
            "EBIT Margin Volatility": {"score": s_ebit, "raw": round(sd_ebit, 2) if sd_ebit is not None else None, "desc": "SD of EBIT margins (pp)"},
        },
    }


def calc_revenue_stability(d: dict) -> dict:
    rev = d["revenue"]
    clean = [v for v in rev if v is not None]

    dd = _drawdown(clean)
    s_dd = score_rev_drawdown_bq(dd)

    mean = sum(clean) / len(clean) if clean else None
    sd = _pop_sd(clean)
    cv = (sd / mean * 100) if (sd is not None and mean and mean != 0) else None
    s_cv = score_rev_volatility(cv)

    score = _weighted([(s_dd, 0.60), (s_cv, 0.40)])
    return {
        "score": score,
        "subs": {
            "Revenue Drawdown": {"score": s_dd, "raw": round(dd, 1) if dd is not None else None, "desc": "Peak-to-trough revenue fall (%)"},
            "Revenue Volatility": {"score": s_cv, "raw": round(cv, 1) if cv is not None else None, "desc": "Coefficient of variation of revenue (%)"},
        },
    }


def calc_business_quality(d: dict) -> dict:
    ms = _try_component(calc_margin_strength, d)
    mstab = _try_component(calc_margin_stability, d)
    rs = _try_component(calc_revenue_stability, d)

    raw = _weighted([(ms["score"], 0.40), (mstab["score"], 0.35), (rs["score"], 0.25)])

    caps = []
    avg_ebitda = ms.get("avg_ebitda_margin")
    if raw is not None and avg_ebitda is not None:
        if avg_ebitda < 10:
            if raw > 6:
                raw = 6.0; caps.append("Avg EBITDA margin <10% → BQ capped at 6")
        elif avg_ebitda < 15:
            if raw > 6.5:
                raw = 6.5; caps.append("Avg EBITDA margin <15% → BQ capped at 6.5")

    score = _clamp(raw)
    return {
        "score": score,
        "caps": caps,
        "components": {
            "Margin Strength": {**ms, "weight": "40%"},
            "Margin Stability": {**mstab, "weight": "35%"},
            "Revenue Stability": {**rs, "weight": "25%"},
        },
    }


# ---------------------------------------------------------------------------
# Growth Quality
# ---------------------------------------------------------------------------

def _growth_rates(values: list) -> list:
    """Year-over-year growth rates (%) from most-recent-first series."""
    rates = []
    for i in range(len(values) - 1):
        if values[i] is not None and values[i + 1] is not None and values[i + 1] != 0:
            rates.append((values[i] / values[i + 1] - 1) * 100)
        else:
            rates.append(None)
    return rates


def calc_growth_rate(d: dict) -> dict:
    rev = d["revenue"]

    # CAGR over 4 years (needs at least 5 data points)
    cagr = None
    rev0, rev4 = _g(rev, 0), _g(rev, 4)
    if rev0 is not None and rev4 is not None and rev4 > 0:
        cagr = ((rev0 / rev4) ** 0.25 - 1) * 100
    s_cagr = score_revenue_cagr(cagr)

    # Recent growth: avg of last 2 YoY growth rates
    rev1, rev2 = _g(rev, 1), _g(rev, 2)
    g1 = (rev0 / rev1 - 1) * 100 if (rev0 is not None and rev1 and rev1 != 0) else None
    g2 = (rev1 / rev2 - 1) * 100 if (rev1 is not None and rev2 and rev2 != 0) else None
    rec_valid = [x for x in [g1, g2] if x is not None]
    recent = sum(rec_valid) / len(rec_valid) if rec_valid else None
    s_recent = score_revenue_cagr(recent)

    # Growth direction: years with growth >= 2%
    rates = _growth_rates(rev)
    dir_count = sum(1 for r in rates if r is not None and r >= 2.0)
    s_dir = score_growth_direction(dir_count)

    score = _weighted([(s_cagr, 0.50), (s_recent, 0.30), (s_dir, 0.20)])
    return {
        "score": score,
        "cagr": cagr,
        "subs": {
            "Revenue CAGR": {"score": s_cagr, "raw": round(cagr, 1) if cagr is not None else None, "desc": "4-year revenue CAGR (%)"},
            "Recent Growth": {"score": s_recent, "raw": round(recent, 1) if recent is not None else None, "desc": "Avg of last 2 YoY growth rates (%)"},
            "Growth Direction": {"score": s_dir, "raw": dir_count, "desc": "Years with growth ≥2%"},
        },
    }


def calc_growth_stability(d: dict) -> dict:
    rev = d["revenue"]
    rates = [r for r in _growth_rates(rev) if r is not None]

    # Volatility: population SD of growth rates
    sd = _pop_sd(rates) if len(rates) >= 2 else None
    s_vol = score_growth_volatility(sd)

    worst = min(rates) if rates else None
    s_ds = score_downside_severity(worst)

    neg_count = sum(1 for r in rates if r < 0)
    s_neg = score_negative_years(neg_count)

    score = _weighted([(s_vol, 0.50), (s_ds, 0.30), (s_neg, 0.20)])
    return {
        "score": score,
        "subs": {
            "Growth Volatility": {"score": s_vol, "raw": round(sd, 1) if sd is not None else None, "desc": "SD of annual revenue growth rates (%)"},
            "Downside Severity": {"score": s_ds, "raw": round(worst, 1) if worst is not None else None, "desc": "Worst single-year revenue growth (%)"},
            "Negative Year Count": {"score": s_neg, "raw": neg_count, "desc": "Years with negative revenue growth"},
        },
    }


def calc_margin_impact(d: dict) -> dict:
    rev = d["revenue"]
    ebitda = d["ebitda"]

    rev0, rev3, rev4 = _g(rev, 0), _g(rev, 3), _g(rev, 4)
    ebitda0, ebitda3 = _g(ebitda, 0), _g(ebitda, 3)

    margin_0 = _div(ebitda0, rev0)
    margin_3 = _div(ebitda3, rev3)
    trend = (margin_0 - margin_3) * 100 if (margin_0 is not None and margin_3 is not None) else None
    s_trend = score_margin_trend_gq(trend)

    # Growth vs margin alignment
    cagr_val = None
    if rev0 and rev4 and rev4 > 0:
        cagr_val = ((rev0 / rev4) ** 0.25 - 1) * 100
    s_align = score_growth_margin_alignment(cagr_val, trend)

    score = _weighted([(s_trend, 0.60), (s_align, 0.40)])
    return {
        "score": score,
        "subs": {
            "Margin Trend": {"score": s_trend, "raw": round(trend, 1) if trend is not None else None, "desc": "EBITDA margin change vs 3 years ago (pp)"},
            "Growth-Margin Alignment": {"score": s_align, "raw": None, "desc": f"Revenue {'growing' if (cagr_val or 0)>0.5 else 'declining' if (cagr_val or 0)<-0.5 else 'flat'} / Margin {'improving' if (trend or 0)>0.5 else 'declining' if (trend or 0)<-0.5 else 'flat'}"},
        },
    }


def calc_growth_cash_support(d: dict) -> dict:
    rev = d["revenue"]
    fcf = _calc_fcf_series(d)

    rev0, rev4 = _g(rev, 0), _g(rev, 4)
    fcf0, fcf4 = _g(fcf, 0), _g(fcf, 4)

    # Growth-cash gap
    rev_cagr = None
    if rev0 and rev4 and rev4 > 0:
        rev_cagr = ((rev0 / rev4) ** 0.25 - 1) * 100

    fcf_cagr = None
    if fcf0 is not None and fcf4 is not None and fcf4 > 0 and fcf0 > 0:
        fcf_cagr = ((fcf0 / fcf4) ** 0.25 - 1) * 100

    gap = (rev_cagr - fcf_cagr) if (rev_cagr is not None and fcf_cagr is not None) else None
    s_gap = score_growth_cash_gap(gap)

    # Alignment consistency: years both rev and FCF growth >= 0
    rev_growth = _growth_rates(rev)
    fcf_growth = _growth_rates(fcf)
    aligned = sum(
        1 for i in range(min(len(rev_growth), len(fcf_growth)))
        if rev_growth[i] is not None and fcf_growth[i] is not None
        and rev_growth[i] >= 0 and fcf_growth[i] >= 0
    )
    s_align = score_alignment_consistency(aligned)

    score = _weighted([(s_gap, 0.70), (s_align, 0.30)])
    return {
        "score": score,
        "subs": {
            "Growth-Cash Gap": {"score": s_gap, "raw": round(gap, 1) if gap is not None else None, "desc": "Revenue CAGR minus FCF CAGR (pp)"},
            "Alignment Consistency": {"score": s_align, "raw": aligned, "desc": "Years both revenue and FCF grew simultaneously"},
        },
    }


def calc_growth_quality(d: dict) -> dict:
    gr = _try_component(calc_growth_rate, d)
    gs = _try_component(calc_growth_stability, d)
    mi = _try_component(calc_margin_impact, d)
    gcs = _try_component(calc_growth_cash_support, d)

    raw = _weighted([(gr["score"], 0.20), (gs["score"], 0.35), (mi["score"], 0.20), (gcs["score"], 0.25)])
    score = _clamp(raw)
    return {
        "score": score,
        "components": {
            "Growth Rate": {**gr, "weight": "20%"},
            "Growth Stability": {**gs, "weight": "35%"},
            "Margin Impact": {**mi, "weight": "20%"},
            "Growth vs Cash": {**gcs, "weight": "25%"},
        },
    }


# ---------------------------------------------------------------------------
# Capital Efficiency
# ---------------------------------------------------------------------------

def calc_capex_intensity(d: dict) -> dict:
    rev = d["revenue"]
    capex = d["capex"]
    n = min(len(rev), len(capex))

    intensities = [_pct(capex[i], rev[i]) for i in range(n)]
    clean = [v for v in intensities if v is not None]
    avg_intensity = sum(clean) / len(clean) if clean else None
    s_avg = score_avg_capex_intensity(avg_intensity)

    sd = _pop_sd(clean)
    s_sd = score_capex_intensity_sd(sd)

    i0, i3 = _g(intensities, 0), _g(intensities, 3)
    trend = (i0 - i3) if (i0 is not None and i3 is not None) else None
    s_trend = score_capex_intensity_trend(trend)

    score = _weighted([(s_avg, 0.50), (s_sd, 0.25), (s_trend, 0.25)])
    return {
        "score": score,
        "subs": {
            "Avg Capex Intensity": {"score": s_avg, "raw": round(avg_intensity, 1) if avg_intensity is not None else None, "desc": "Average capex as % of revenue"},
            "Capex Intensity Stability": {"score": s_sd, "raw": round(sd, 2) if sd is not None else None, "desc": "SD of capex intensity (pp)"},
            "Capex Intensity Trend": {"score": s_trend, "raw": round(trend, 1) if trend is not None else None, "desc": "Capex intensity change vs 3 years ago (pp)"},
        },
    }


def calc_capex_vs_depr(d: dict) -> dict:
    capex = d["capex"]
    depr = d["depreciation"]
    n = min(len(capex), len(depr))

    ratios = [_div(capex[i], depr[i]) if (capex[i] is not None and depr[i] and depr[i] != 0) else None
              for i in range(n)]
    clean = [v for v in ratios if v is not None]
    avg_ratio = sum(clean) / len(clean) if clean else None
    s_avg = score_avg_capex_depr(avg_ratio)

    sd = _pop_sd(clean)
    s_sd = score_capex_depr_sd(sd)

    r0, r3 = _g(ratios, 0), _g(ratios, 3)
    trend = (r0 - r3) if (r0 is not None and r3 is not None) else None
    s_trend = score_capex_depr_trend(trend)

    score = _weighted([(s_avg, 0.60), (s_sd, 0.20), (s_trend, 0.20)])
    return {
        "score": score,
        "subs": {
            "Avg Capex/Depreciation": {"score": s_avg, "raw": round(avg_ratio, 2) if avg_ratio is not None else None, "desc": "Avg ratio of capex to depreciation (1.0 = maintenance)"},
            "Ratio Stability": {"score": s_sd, "raw": round(sd, 2) if sd is not None else None, "desc": "SD of capex/depreciation ratio"},
            "Ratio Trend": {"score": s_trend, "raw": round(trend, 2) if trend is not None else None, "desc": "Change in capex/depr ratio vs 3 years ago"},
        },
    }


def calc_roce_pillar(d: dict) -> dict:
    ebit = d["ebit"]
    assets = d["total_assets"]
    curr_liab = d["current_liabilities"]
    n = min(len(ebit), len(assets), len(curr_liab))

    roces = []
    for i in range(n):
        if ebit[i] is not None and assets[i] is not None:
            cap_emp = (assets[i] or 0) - (curr_liab[i] or 0) if curr_liab[i] is not None else assets[i]
            roces.append(_pct(ebit[i], cap_emp) if cap_emp else None)
        else:
            roces.append(None)

    clean = [v for v in roces if v is not None]
    avg_roce = sum(clean) / len(clean) if clean else None
    s_avg = score_avg_roce(avg_roce)

    sd = _pop_sd(clean)
    s_sd = score_roce_sd(sd)

    r0, r3 = _g(roces, 0), _g(roces, 3)
    trend = (r0 - r3) if (r0 is not None and r3 is not None) else None
    s_trend = score_roce_trend(trend)

    score = _weighted([(s_avg, 0.40), (s_sd, 0.20), (s_trend, 0.40)])
    return {
        "score": score,
        "subs": {
            "Average ROCE": {"score": s_avg, "raw": round(avg_roce, 1) if avg_roce is not None else None, "desc": "Avg return on capital employed (%)"},
            "ROCE Stability": {"score": s_sd, "raw": round(sd, 1) if sd is not None else None, "desc": "SD of ROCE (pp)"},
            "ROCE Trend": {"score": s_trend, "raw": round(trend, 1) if trend is not None else None, "desc": "ROCE change vs 3 years ago (pp)"},
        },
    }


def calc_capital_efficiency(d: dict) -> dict:
    ci = _try_component(calc_capex_intensity, d)
    cvd = _try_component(calc_capex_vs_depr, d)
    roce = _try_component(calc_roce_pillar, d)

    raw = _weighted([(ci["score"], 0.40), (cvd["score"], 0.30), (roce["score"], 0.30)])
    score = _clamp(raw)
    return {
        "score": score,
        "components": {
            "Capex Intensity": {**ci, "weight": "40%"},
            "Capex vs Depreciation": {**cvd, "weight": "30%"},
            "ROCE": {**roce, "weight": "30%"},
        },
    }


# ---------------------------------------------------------------------------
# Hard Stops
# ---------------------------------------------------------------------------

def check_hard_stops(d: dict) -> List[str]:
    stops = []
    rev = d["revenue"]
    ebitda = d["ebitda"]
    ebit = d["ebit"]
    interest = d["interest_expense"]
    debt = d["long_term_debt"]
    cash = d["cash"]
    equity = d["equity"]
    fcf = _calc_fcf_series(d)

    # Net Debt/EBITDA > 4.5x
    if debt[0] is not None and ebitda[0] and ebitda[0] > 0:
        nd = (debt[0] or 0) - (cash[0] or 0)
        if nd / ebitda[0] > 4.5:
            stops.append(f"Net Debt/EBITDA > 4.5x ({nd/ebitda[0]:.1f}x)")

    # FCF < 0 for 3 consecutive years
    for i in range(3):
        if all(fcf[j] is not None and fcf[j] < 0 for j in range(i, i + 3)):
            stops.append("FCF negative for 3+ consecutive years")
            break

    # EBIT/Interest < 2.0x
    if ebit[0] is not None and interest[0] and interest[0] > 0:
        cov = ebit[0] / interest[0]
        if cov < 2.0:
            stops.append(f"EBIT/Interest < 2.0x ({cov:.1f}x)")

    # EBITDA margin decline > 8pp over 3 years
    ebitda3, rev3 = _g(ebitda, 3), _g(rev, 3)
    if ebitda[0] is not None and rev[0] and ebitda3 is not None and rev3:
        m0 = ebitda[0] / rev[0] * 100
        m3 = ebitda3 / rev3 * 100
        if m3 - m0 > 8:
            stops.append(f"EBITDA margin declined {m3-m0:.1f}pp over 3 years")

    # Net Debt/EBITDA > 3.5x AND EBITDA declining YoY
    ebitda1 = _g(ebitda, 1)
    if debt[0] is not None and ebitda[0] and ebitda[0] > 0 and ebitda1 is not None:
        nd = (debt[0] or 0) - (cash[0] or 0)
        if nd / ebitda[0] > 3.5 and ebitda[0] < ebitda1:
            stops.append(f"Net Debt/EBITDA > 3.5x AND EBITDA declining YoY")

    # CapEx/Revenue > 15% AND weak FCF (negative)
    if d["capex"][0] is not None and rev[0] and fcf[0] is not None:
        cx_pct = d["capex"][0] / rev[0] * 100
        if cx_pct > 15 and fcf[0] < 0:
            stops.append(f"CapEx/Revenue {cx_pct:.1f}% > 15% with negative FCF")

    # EBITDA volatility ±30% regularly (2+ years with >30% YoY change)
    if ebitda and any(v is not None for v in ebitda):
        big_swings = 0
        for i in range(min(4, len(ebitda) - 1)):
            if ebitda[i] is not None and ebitda[i + 1] is not None and ebitda[i + 1] != 0:
                chg = abs(ebitda[i] / ebitda[i + 1] - 1) * 100
                if chg > 30:
                    big_swings += 1
        if big_swings >= 2:
            stops.append(f"EBITDA volatility >30% in {big_swings} of last 4 years")

    # Shareholders' equity < 0
    if equity[0] is not None and equity[0] < 0:
        stops.append(f"Shareholders' equity negative ({equity[0]/1000:.1f}B)")

    return stops


# ---------------------------------------------------------------------------
# Overall Score
# ---------------------------------------------------------------------------

def calc_overall(pillar_scores: dict, hard_stops: list) -> dict:
    fr = pillar_scores["financial_risk"]
    cg = pillar_scores["cash_generation"]
    bq = pillar_scores["business_quality"]
    gq = pillar_scores["growth_quality"]
    ce = pillar_scores["capital_efficiency"]

    raw = _weighted([(fr, 0.25), (cg, 0.20), (bq, 0.25), (gq, 0.15), (ce, 0.15)])
    if raw is None:
        return {"score": None, "recommendation": "INSUFFICIENT DATA", "caps": [], "penalties": []}

    caps = []
    penalties = []

    # Pillar-level caps
    if bq is not None and bq < 6:
        if raw > 6:
            raw = 6.0; caps.append("BQ < 6 → Overall capped at 6")
    if fr is not None and fr < 5.5:
        if raw > 5.5:
            raw = 5.5; caps.append("FR < 5.5 → Overall capped at 5.5")

    # Multi-pillar penalty
    scores_list = [s for s in [fr, cg, bq, gq, ce] if s is not None]
    below_5 = sum(1 for s in scores_list if s < 5)
    below_4 = sum(1 for s in scores_list if s < 4)
    below_3 = sum(1 for s in scores_list if s < 3)

    if below_3 >= 2:
        raw -= 2; penalties.append("2+ pillars < 3 → -2")
    elif below_4 >= 2:
        raw -= 1.25; penalties.append("2+ pillars < 4 → -1.25")
    elif below_5 >= 2:
        raw -= 0.5; penalties.append("2+ pillars < 5 → -0.5")

    score = _clamp(raw)

    # Recommendation
    if hard_stops:
        rec = "HARD STOP"
    elif (score >= 7.0
          and (fr is None or fr >= 6.0)
          and all((s is None or s >= 4.0) for s in scores_list)
          and (bq is not None and bq >= 7.0 or cg is not None and cg >= 7.0)):
        rec = "BUY"
    elif score >= 5.0 and sum(1 for s in scores_list if s <= 4.0) <= 1:
        rec = "HOLD"
    else:
        rec = "SELL"

    return {"score": round(score, 2), "recommendation": rec, "caps": caps, "penalties": penalties}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def _try_pillar(fn, d):
    """Call a pillar function; on any exception return a null-score stub."""
    try:
        return fn(d)
    except Exception as exc:
        return {"score": None, "components": {}, "error": f"{type(exc).__name__}: {exc}"}


_SECTOR_MESSAGE = (
    "This company operates in a sector (e.g. banking, insurance) that uses a "
    "different financial reporting structure. Equity Engine is optimised for "
    "non-financial companies and cannot produce a reliable score without EBIT "
    "and EBITDA data."
)


def _is_financial_sector(data: dict) -> bool:
    """
    Return True when the company's financial data indicates a financial-sector
    company (bank, insurer, investment firm) that cannot be reliably scored.

    Four complementary signals — any one is sufficient:

    1. EBIT or EBITDA series is entirely absent (all None values).

    2. EBITDA was constructed via the EBIT + D&A fallback rather than read
       from a direct Macrotrends income-statement row.  Macrotrends lists
       EBITDA explicitly for every standard non-financial company; its absence
       as a direct field is a reliable indicator of financial-company reporting
       structure (e.g. JPMorgan has no EBITDA row — only "Operating Income").

    3. EBITDA ≈ EBIT for every available year (D&A add-back < 0.5 % of
       revenue).  Some financial companies (e.g. Goldman Sachs at certain
       periods) have an EBITDA row on Macrotrends that equals Operating Income
       with no meaningful D&A added back.  Below 0.5 % of revenue across every
       year is implausible for any manufacturing, tech, or service company.

    4. Current liabilities > 60 % of total assets across every year.  Banks
       and investment firms park customer deposits as current liabilities,
       pushing this ratio to 70-85 %.  No non-financial company maintains this
       level — even heavily leveraged industrials stay below 50 %.
    """
    ebit   = data.get("ebit",   [])
    ebitda = data.get("ebitda", [])
    rev    = data.get("revenue", [])

    # Signal 1: entirely absent series
    if not ebit   or all(v is None for v in ebit):
        return True
    if not ebitda or all(v is None for v in ebitda):
        return True

    # Signal 2: EBITDA was computed via fallback, not directly reported
    if data.get("ebitda_from_fallback"):
        return True

    # Signal 3: EBITDA ≈ EBIT every year (no meaningful D&A add-back)
    n = min(len(ebit), len(ebitda), len(rev))
    da_fracs = [
        (ebitda[i] - ebit[i]) / rev[i]
        for i in range(n)
        if ebit[i] is not None and ebitda[i] is not None
        and rev[i] is not None and rev[i] > 0
    ]
    if da_fracs and all(abs(f) < 0.005 for f in da_fracs):
        return True

    # Signal 4: bank balance-sheet fingerprint.
    # Customer deposits are classified as current liabilities → ratio > 60 %.
    curr_liab    = data.get("current_liabilities", [])
    total_assets = data.get("total_assets", [])
    if curr_liab and total_assets:
        cl_ratios = [
            c / a
            for c, a in zip(curr_liab, total_assets)
            if c is not None and a is not None and a > 0
        ]
        if cl_ratios and all(r > 0.60 for r in cl_ratios):
            return True

    return False


def analyse(data: dict) -> dict:
    """Run full analysis. data = output of scraper.get_company_data()."""
    if _is_financial_sector(data):
        return {
            "years": data.get("years", []),
            "unsupported_sector": True,
            "sector_message": _SECTOR_MESSAGE,
            "overall": {"score": None, "recommendation": "NOT RATED", "caps": [], "penalties": []},
            "hard_stops": [],
            "pillars": {},
        }

    fr_result = _try_pillar(calc_financial_risk, data)
    cg_result = _try_pillar(calc_cash_generation, data)
    bq_result = _try_pillar(calc_business_quality, data)
    gq_result = _try_pillar(calc_growth_quality, data)
    ce_result = _try_pillar(calc_capital_efficiency, data)

    pillar_scores = {
        "financial_risk": fr_result["score"],
        "cash_generation": cg_result["score"],
        "business_quality": bq_result["score"],
        "growth_quality": gq_result["score"],
        "capital_efficiency": ce_result["score"],
    }

    hard_stops = check_hard_stops(data)
    overall = calc_overall(pillar_scores, hard_stops)

    return {
        "years": data.get("years", []),
        "overall": overall,
        "hard_stops": hard_stops,
        "pillars": {
            "Financial Risk": {**fr_result, "pillar_weight": "25%"},
            "Cash Generation": {**cg_result, "pillar_weight": "20%"},
            "Business Quality": {**bq_result, "pillar_weight": "25%"},
            "Growth Quality": {**gq_result, "pillar_weight": "15%"},
            "Capital Efficiency": {**ce_result, "pillar_weight": "15%"},
        },
    }
