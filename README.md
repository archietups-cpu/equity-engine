# Equity Engine

A Python-based fundamental equity analysis tool that scrapes historical financial statement data and scores companies across five pillars of business quality — built as a portfolio project for investment banking and finance applications.

## Overview

Equity Engine evaluates companies the way a fundamentals-driven equity analyst would: prioritising financial safety, consistent cash generation, and capital efficiency over headline growth. Rather than relying on a single metric or screening tool, it combines five weighted pillars into a single composite score (1–10) with a clear Buy / Hold / Sell signal, while remaining fully transparent about how each score was derived.

The model encodes a specific investment philosophy:

1. Financial safety before growth
2. Consistent growth over rapid growth
3. Free cash flow over accounting earnings
4. Margin preservation over revenue growth
5. Sustainable, internally-funded growth
6. Capital-light business models over capital-heavy ones

## How it works

1. **Search** — enter a company name or ticker
2. **Scrape** — the engine pulls historical income statement, balance sheet, and cash flow data from [Macrotrends](https://www.macrotrends.net)
3. **Score** — five pillar calculations run against the data, each built from multiple sub-metrics
4. **Output** — an overall score, individual pillar breakdowns, and a drill-down into every underlying calculation and what it means

## The five pillars

| Pillar | Weight | Measures |
|---|---|---|
| **Financial Risk** | 25% | Leverage, interest coverage, FCF coverage, earnings stability, equity buffer |
| **Cash Generation** | 20% | Cash conversion, FCF margin level/stability/trend, FCF drawdown risk |
| **Business Quality** | 25% | Margin strength, margin stability, revenue stability |
| **Growth Quality** | 15% | Growth rate, growth stability, margin impact of growth, growth vs. cash support |
| **Capital Efficiency** | 15% | Average ROCE, ROCE stability, ROCE trend |

### Penalty and hard stop rules

The model includes rules-based caps designed to flag structurally weak businesses regardless of how strong they look elsewhere — for example, a Financial Risk score below 5.5 or a Business Quality score below 6 caps the maximum overall score, and severe red flags (e.g. sustained margin destruction, extreme EBITDA volatility) trigger an outright Hard Stop. This mirrors how credit risk is typically assessed before equity upside is considered.

## Features

- **Solo search** — full pillar breakdown and sub-metric detail for any single company
- **Comparison mode** — analyse up to 5 companies side by side, filterable by signal (Buy/Hold/Sell) or pillar score thresholds
- **Sector detection** — automatically flags companies (e.g. banks, insurers) that don't report standard operating metrics like EBIT/EBITDA, rather than producing a misleading score
- **Transparent calculations** — every sub-score is expandable to show the underlying data, formula, and scoring band used

## Example outputs

| Company | Overall Score | Signal |
|---|---|---|
| Unilever | 7.49 | Buy |
| Tesco | 5.12 | Hard Stop |
| Anglo American | 4.53 | Hard Stop |

These three companies were used as calibration benchmarks throughout development, spanning a quality consumer staples compounder, a structurally weaker retailer, and a cyclical, capital-intensive miner.

## Tech stack

- **Backend:** Python, Flask
- **Scraping:** BeautifulSoup / Selenium
- **Frontend:** HTML, CSS, JavaScript

## Running locally

```bash
git clone https://github.com/archietups-cpu/equity-engine.git
cd equity-engine
pip install -r requirements.txt
python3 app.py
```

Then open `http://127.0.0.1:5000` (or the port shown in your terminal) in a browser.

## Known limitations

- Currently relies on Macrotrends as its sole data source — coverage is strongest for US-listed and major dual-listed companies; some LSE-only companies may not be found
- Not designed for financial sector companies (banks, insurers, asset managers) whose reporting structure differs fundamentally from operating companies
- Comparison mode is capped at 4 companies to avoid being rate-limited by the data source
- Scoring bands were calibrated on a limited initial set of companies and are an ongoing work in progress

## Roadmap

- [ ] Bulk screener mode to scan a larger universe of companies for Buy/Sell signals
- [ ] Secondary data source for broader international coverage
- [ ] Sector-specific scoring framework for financial companies

## Background

This project was built to develop a genuine, first-principles understanding of fundamental equity analysis ahead of investment banking spring week and analyst applications — both the financial reasoning behind the scoring framework and the practical engineering of turning that framework into a working tool.
