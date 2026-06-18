"""
Macrotrends financial data scraper.

Data source: three HTML pages per company (income-statement, balance-sheet,
cash-flow-statement). Each page embeds annual figures as JSON row objects:
  {"field_name": "Revenue", "2024-12-31": "65749.00", ...}
Values are in millions USD (Macrotrends' native unit).
"""

import difflib
import json
import re
import threading
import time
from typing import Optional, Dict, List
import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.macrotrends.net/",
}

# Thread-local sessions so parallel Flask requests never share connection state.
_thread_local = threading.local()

# Global lock that serialises all Macrotrends HTTP fetching.
#
# Why: when comparison mode fires N parallel /analyse requests, Flask spawns N
# threads.  Without this lock all threads hammer Macrotrends simultaneously,
# triggering rate-limiting that silently returns empty pages for some companies.
# The result is non-deterministic null scores that differ from solo-search scores.
#
# With this lock each company's three page-fetches run exclusively, one company
# at a time, giving the same environment as a solo search and therefore identical
# scores.  The cost is serial execution (~30 s per company), which the frontend
# already handles via per-company progress updates.
_macrotrends_lock = threading.Lock()

# Companies that are frequently searched but fail to appear via the Macrotrends
# search API — either because they are listed under ADR/OTC tickers, or because
# their names contain hyphens or other characters that break the API query.
# Verified slugs confirmed by direct page fetch (revenue field present).
_KNOWN: List[Dict] = [
    {"ticker": "KO",    "name": "Coca-Cola",            "slug": "coca-cola"},
    {"ticker": "TSCDY", "name": "Tesco",                "slug": "tesco"},
    {"ticker": "UL",    "name": "Unilever",             "slug": "unilever"},
    {"ticker": "NGLOY", "name": "Anglo American",       "slug": "anglo-american"},
    {"ticker": "RYCEY", "name": "Rolls-Royce Holdings", "slug": "rolls-royce-holdings"},
    {"ticker": "CCL",   "name": "Carnival Corporation", "slug": "carnival"},
    {"ticker": "HSBC",  "name": "HSBC",                 "slug": "hsbc"},
    {"ticker": "VOD",   "name": "Vodafone Group",       "slug": "vodafone-group"},
    {"ticker": "DEO",   "name": "Diageo",               "slug": "diageo"},
    {"ticker": "BP",    "name": "BP",                   "slug": "bp"},
    {"ticker": "SHEL",  "name": "Shell",                "slug": "shell"},
    {"ticker": "AZN",   "name": "AstraZeneca",          "slug": "astrazeneca"},
    {"ticker": "GSK",   "name": "GSK",                  "slug": "gsk"},
    {"ticker": "BAESY", "name": "BAE Systems",          "slug": "bae-systems"},
    {"ticker": "CMPGY", "name": "Compass Group",        "slug": "compass-group"},
]

_KNOWN_SUFFIXES = (
    " holdings", " corporation", " corp", " group", " plc", " ltd",
    " limited", " inc", " co", " company", " cruise lines", " cruises",
)


def _norm_co(s: str) -> str:
    """Lowercase, remove punctuation, strip common company-name suffixes."""
    s = re.sub(r"[^\w\s]", " ", s.lower())
    s = re.sub(r"\s+", " ", s).strip()
    for sfx in _KNOWN_SUFFIXES:
        if s.endswith(sfx):
            s = s[: -len(sfx)].strip()
            break
    return s


def _known_matches(query: str) -> List[Dict]:
    """Return hardcoded entries whose name or ticker fuzzy-matches the query."""
    q = _norm_co(query)
    results: List[Dict] = []
    seen: set = set()
    for entry in _KNOWN:
        n = _norm_co(entry["name"])
        t = entry["ticker"].lower()
        # Exact ticker match, or name prefix/substring match (min 3 chars to avoid noise)
        if q == t or (len(q) >= 3 and (q in n or n.startswith(q) or q.startswith(n))):
            if entry["ticker"] not in seen:
                seen.add(entry["ticker"])
                results.append({
                    "ticker": entry["ticker"],
                    "name":   entry["name"],
                    "slug":   entry["slug"],
                })
    return results


def _query_variations(query: str) -> List[str]:
    """Return the original query plus variations to try against the Macrotrends API."""
    vs: List[str] = []

    def _add(v: str) -> None:
        v = v.strip()
        if v and v not in vs:
            vs.append(v)

    _add(query)
    _add(query.replace("-", " "))           # "Coca-Cola" → "Coca Cola"
    _add(re.sub(r"[^\w\s]", "", query))    # strip all special chars
    return vs


def _name_sim(query: str, candidate: str) -> float:
    """SequenceMatcher similarity between normalised company names (0–1)."""
    return difflib.SequenceMatcher(None, _norm_co(query), _norm_co(candidate)).ratio()


def _session() -> requests.Session:
    """Return a per-thread Session — safe under Flask's threaded dev server."""
    if not hasattr(_thread_local, "session"):
        s = requests.Session()
        s.headers.update(HEADERS)
        _thread_local.session = s
    return _thread_local.session


def search_company(query: str) -> List[Dict]:
    """Return list of {ticker, name, slug} matches from Macrotrends.

    1. Query the Macrotrends search API using the original query and variations.
       Deduplicate by ticker and sort by name similarity — closest match first.
    2. Fall back to the hardcoded dictionary only when the API returns nothing.
       (Handles companies that Macrotrends' search index doesn't surface.)
    """
    url = "https://www.macrotrends.net/assets/php/all_pages_query.php"
    seen: set = set()
    results: List[Dict] = []

    for q in _query_variations(query):
        try:
            r = _session().get(url, params={"q": q}, timeout=10)
            r.raise_for_status()
            raw = r.json()
            for item in raw:
                item_url = item.get("url", "")
                parts = item_url.strip("/").split("/")
                if len(parts) < 5 or parts[0] != "stocks":
                    continue
                ticker = parts[2].upper()
                slug = parts[3]
                if ticker in seen:
                    continue
                seen.add(ticker)
                raw_name = item.get("name", "")
                # Strip ticker in parentheses and any trailing metric label.
                # Handles: "Reckitt Benckiser Group (RBGPF) Revenue"
                #       and "Apple Inc - Net Income"
                name = re.sub(r"\s*\([A-Z][A-Z0-9.]{0,6}\).*$", "", raw_name)
                name = re.sub(r"\s+-\s+.*$", "", name).strip() or ticker
                results.append({"ticker": ticker, "name": name, "slug": slug})
        except Exception:
            pass

    if results:
        results.sort(key=lambda c: _name_sim(query, c["name"]), reverse=True)
        return results[:10]

    # API returned nothing — fall back to hardcoded lookup
    return _known_matches(query)


# ---------------------------------------------------------------------------
# Row parsing from financial statement HTML pages
# ---------------------------------------------------------------------------

def _parse_rows(html: str) -> Dict[str, Dict[int, float]]:
    """
    Extract all data rows from a Macrotrends financial statement page.
    Returns {clean_field_name: {year: value_in_millions}}.
    """
    result: Dict[str, Dict[int, float]] = {}

    for m in re.finditer(r'\{"field_name":', html):
        start = m.start()
        depth = 0
        end = start
        for i, ch in enumerate(html[start: start + 50000]):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = start + i + 1
                    break
        if end <= start:
            continue

        try:
            obj = json.loads(html[start:end])
        except (json.JSONDecodeError, ValueError):
            continue

        raw_field = obj.get("field_name", "")
        field = re.sub(r"<[^>]+>", "", raw_field).strip()
        if not field:
            continue

        values: Dict[int, float] = {}
        for k, v in obj.items():
            if k in ("field_name", "popup_icon") or not v:
                continue
            year_m = re.match(r"^(\d{4})-", k)
            if not year_m:
                continue
            year = int(year_m.group(1))
            try:
                values[year] = float(v)
            except (TypeError, ValueError):
                continue

        if values:
            result[field] = values

    return result


def _fetch_page_rows(ticker: str, slug: str, statement: str,
                     retries: int = 3) -> Dict[str, Dict[int, float]]:
    """Fetch one financial statement page, retrying on failure or empty result."""
    url = f"https://www.macrotrends.net/stocks/charts/{ticker}/{slug}/{statement}"
    for attempt in range(retries + 1):
        if attempt > 0:
            time.sleep(2.5 * attempt)  # 2.5s, 5s, 7.5s
        try:
            r = _session().get(url, params={"freq": "A"}, timeout=30)
            if r.status_code == 200:
                rows = _parse_rows(r.text)
                if rows:
                    return rows
        except Exception:
            pass
    return {}


# ---------------------------------------------------------------------------
# Field-name lookup helpers
# ---------------------------------------------------------------------------

def _normalize(s: str) -> str:
    """Strip punctuation, collapse whitespace, lowercase — for fuzzy field-name comparison."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).lower().strip()


def _find(rows: Dict[str, Dict[int, float]],
          *candidates: str) -> Optional[Dict[int, float]]:
    """
    Return the first matching row.

    Priority:
      1. Case-insensitive exact match
      2. Punctuation-normalised exact match  (handles "Property, Plant, And Equipment"
         vs "Property Plant And Equipment")
      3. Substring partial match across all candidates, preferring shorter field
         names (shorter = more likely to be the aggregate/total row, not a sub-line)
    """
    lower_map: Dict[str, Dict[int, float]] = {f.lower(): v for f, v in rows.items()}
    norm_map:  Dict[str, Dict[int, float]] = {_normalize(f): v for f, v in rows.items()}

    # Pass 1: exact, case-insensitive
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]

    # Pass 2: normalised exact (strips punctuation/commas)
    for c in candidates:
        key = _normalize(c)
        if key in norm_map:
            return norm_map[key]

    # Pass 3: substring — collect all matches across all candidates, pick shortest
    all_matches: List = []
    seen_fields: set = set()
    for c in candidates:
        key = _normalize(c)
        for f, v in rows.items():
            if f not in seen_fields and key in _normalize(f):
                all_matches.append((f, v))
                seen_fields.add(f)

    if all_matches:
        # Shortest field name most likely represents the aggregate total
        all_matches.sort(key=lambda x: len(x[0]))
        return all_matches[0][1]

    return None


def _to_series(data: Optional[Dict[int, float]], years: List[int]) -> List[Optional[float]]:
    """Map a {year: value} dict to an ordered list aligned with `years`."""
    if not data:
        return [None] * len(years)
    return [data.get(y) for y in years]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def get_company_data(ticker: str, slug: str) -> Dict:
    """
    Scrape all required financial data from Macrotrends.
    Returns aligned series (most recent first, index 0 = latest year).
    All values in millions USD.
    """
    # Acquire the global lock so only one company's pages are fetched at a time.
    # This prevents Macrotrends rate-limiting under concurrent comparison requests
    # and guarantees comparison scores are identical to solo-search scores.
    with _macrotrends_lock:
        time.sleep(0.5)
        income   = _fetch_page_rows(ticker, slug, "income-statement")
        time.sleep(1.5)
        balance  = _fetch_page_rows(ticker, slug, "balance-sheet")
        time.sleep(2.0)
        cashflow = _fetch_page_rows(ticker, slug, "cash-flow-statement")

    # ── Revenue (year anchor) ────────────────────────────────────────
    rev_data = _find(income,
                     "Revenue", "Revenues",
                     "Total Revenue", "Total Revenues",
                     "Net Revenue", "Net Revenues",
                     "Net Sales", "Total Net Revenue", "Total Net Sales",
                     "Sales", "Total Sales")
    if not rev_data:
        raise ValueError(f"No revenue data found for {ticker}. Check the ticker/slug.")

    # ── Year alignment: intersect income with balance sheet ──────────
    assets_check = _find(balance, "Total Assets", "Assets")
    if assets_check:
        common = sorted(set(rev_data.keys()) & set(assets_check.keys()), reverse=True)
    else:
        common = sorted(rev_data.keys(), reverse=True)

    if len(common) < 3:
        raise ValueError(
            f"Only {len(common)} years of overlapping data for {ticker} — need at least 3."
        )
    years = common[:5]

    # ── Income statement fields ──────────────────────────────────────
    ebit_data = _find(income,
                      "EBIT", "Ebit",
                      "Operating Income", "Operating Profit",
                      "Income From Operations", "Profit From Operations",
                      "Operating Earnings")

    ebitda_data = _find(income,
                        "EBITDA", "Ebitda",
                        "Adjusted EBITDA")

    nonop_data = _find(income,
                       "Total Non-Operating Income/Expense",
                       "Non-Operating Income/Expense",
                       "Non Operating Income",
                       "Other Income Expense",
                       "Total Other Income Expense")

    # ── Balance sheet fields ─────────────────────────────────────────
    cash_data   = _find(balance,
                        "Cash On Hand", "Cash And Cash Equivalents",
                        "Cash And Short Term Investments",
                        "Cash", "Cash Equivalents")
    assets_data = assets_check

    curr_liab_data = _find(balance,
                            "Total Current Liabilities", "Current Liabilities")

    equity_data = _find(balance,
                        "Share Holder Equity", "Total Share Holder Equity",
                        "Shareholders Equity", "Stockholders Equity",
                        "Total Stockholders Equity", "Total Equity",
                        "Total Shareholders Equity")

    _ltd_candidate = _find(balance, "Long Term Debt")
    if _ltd_candidate and any(y in _ltd_candidate for y in years):
        ltd_data = _ltd_candidate
    else:
        ltd_data = _find(balance,
                         "Other Non-Current Liabilities",
                         "Total Long Term Liabilities",
                         "Long-Term Liabilities",
                         "Non Current Liabilities",
                         "Total Non Current Liabilities")

    # ── Cash flow fields ─────────────────────────────────────────────
    ocf_data = _find(cashflow,
                     "Cash Flow From Operating Activities",
                     "Operating Cash Flow",
                     "Net Cash Provided By Operating Activities",
                     "Net Cash From Operating Activities",
                     "Cash Generated From Operating Activities",
                     "Cash Flows From Operating Activities")

    capex_data = _find(cashflow,
                       "Net Change In Property, Plant, And Equipment",
                       "Capital Expenditures",
                       "Purchases Of Property",
                       "Purchase Of Property Plant And Equipment",
                       "Purchases Of Property Plant And Equipment",
                       "Property Plant And Equipment Purchases",
                       "Capital Expenditure",
                       "Capex",
                       "Acquisition Of Fixed Assets",
                       "Purchase Of Fixed Assets")

    depr_data = _find(cashflow,
                      "Total Depreciation And Amortization - Cash Flow",
                      "Depreciation And Amortization",
                      "Depreciation & Amortization",
                      "Depreciation",
                      "Amortization",
                      "D&A")

    wc_data = _find(cashflow,
                    "Total Change In Assets/Liabilities",
                    "Change In Working Capital",
                    "Changes In Working Capital",
                    "Changes In Operating Assets And Liabilities",
                    "Net Change In Working Capital",
                    "Change In Operating Assets And Liabilities")

    # ── EBITDA fallback: compute from EBIT + D&A when not directly available ──
    # Covers companies (e.g. some US GAAP filers) where Macrotrends omits the
    # EBITDA row but publishes EBIT and D&A separately.
    # NOTE: track whether the fallback was used — the calculator uses this flag
    # to detect financial companies (banks/insurers never have a direct EBITDA
    # row on Macrotrends, so the fallback being triggered is a sector signal).
    ebitda_from_fallback = False
    if not ebitda_data and ebit_data and depr_data:
        computed: Dict[int, float] = {}
        for y in set(list(ebit_data.keys()) + list(depr_data.keys())):
            e = ebit_data.get(y)
            d = depr_data.get(y)
            if e is not None and d is not None:
                computed[y] = e + d
        if computed:
            ebitda_data = computed
            ebitda_from_fallback = True

    # ── Build aligned series ─────────────────────────────────────────
    def series(data: Optional[Dict[int, float]]) -> List[Optional[float]]:
        return _to_series(data, years)

    # Interest expense: derive from non-operating income/expense
    raw_nonop = series(nonop_data)
    interest_series = [
        max(abs(v), 1.0) if v is not None else None
        for v in raw_nonop
    ]

    # CapEx: Macrotrends' "Net Change in PP&E" is negative (cash outflow) — take abs
    raw_capex = series(capex_data)
    capex_series = [abs(v) if v is not None else None for v in raw_capex]

    _ocf0   = ocf_data.get(years[0])   if ocf_data   else None
    _capex0 = capex_data.get(years[0]) if capex_data else None
    _fcf0   = (_ocf0 - abs(_capex0)) if (_ocf0 is not None and _capex0 is not None) else None
    print(
        f"[ScraperDebug] {ticker}/{slug}  year={years[0]}"
        f"  OCF={_ocf0}  CapEx(raw)={_capex0}  CapEx(abs)={abs(_capex0) if _capex0 is not None else None}"
        f"  FCF(OCF-abs(CapEx))={_fcf0}"
    )

    return {
        "years":               years,
        "revenue":             series(rev_data),
        "ebitda":              series(ebitda_data),
        "ebit":                series(ebit_data),
        "interest_expense":    interest_series,
        "total_assets":        series(assets_data),
        "current_liabilities": series(curr_liab_data),
        "long_term_debt":      series(ltd_data),
        "cash":                series(cash_data),
        "equity":              series(equity_data),
        "operating_cf":        series(ocf_data),
        "capex":               capex_series,
        "depreciation":        series(depr_data),
        "wc_change":           series(wc_data),
        # True when EBITDA was synthesised from EBIT + D&A rather than read
        # directly from the Macrotrends income statement row.  Used by the
        # calculator to detect financial-sector companies (banks/insurers).
        "ebitda_from_fallback": ebitda_from_fallback,
    }
