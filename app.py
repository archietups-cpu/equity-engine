"""Flask backend for the equity analysis engine."""

from flask import Flask, request, jsonify, render_template
from scraper import search_company, get_company_data
from calculator import analyse

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return jsonify([])
    results = search_company(query)
    return jsonify(results[:10])


@app.route("/analyse", methods=["POST"])
def run_analysis():
    body = request.get_json(force=True)
    ticker = body.get("ticker", "").strip().upper()
    slug = body.get("slug", "").strip()
    name = body.get("name", ticker)

    if not ticker or not slug:
        return jsonify({"error": "ticker and slug required"}), 400

    try:
        data = get_company_data(ticker, slug)
    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception as e:
        return jsonify({"error": f"Scraping failed: {e}"}), 500

    try:
        results = analyse(data)
    except Exception as e:
        return jsonify({"error": f"Analysis failed: {e}"}), 500

    results["company"] = {"ticker": ticker, "slug": slug, "name": name}
    return jsonify(results)


if __name__ == "__main__":
    app.run(debug=True, port=5001)
