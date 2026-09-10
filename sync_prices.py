import os
import requests
import psycopg2
from psycopg2.extras import execute_batch

DATABASE_URL = os.getenv("DATABASE_URL")

# Maps legacy, alternate, or renamed tickers to their active EGX scanner symbol
TICKER_ALIASES = {
    "QNBA": "QNBF",   # QNB Alahli
    "MNHD": "MASR",   # Madinet Masr for Housing & Development
    "AUTO": "GBCO",   # GB Corp
    "OTMT": "OIH",    # Orascom Investment Holding
    "COMI": "COMI",
    "TMGH": "TMGH",
    "SWDY": "SWDY",
    "HRHO": "HRHO",
    "ETEL": "ETEL",
    "UBEG": "UBEE",   # United Bank
}

def run_sync():
    print("Fetching EGX closing prices...")
    tv_url = "https://scanner.tradingview.com/egypt/scan"
    payload = {
        "filter": [],
        "options": {"lang": "en"},
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": ["name", "close"],
        "sort": {"sortBy": "name", "sortOrder": "asc"},
        "range": [0, 500]
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    res = requests.post(tv_url, json=payload, headers=headers, timeout=20)
    res.raise_for_status()
    tv_data = res.json().get("data", [])

    price_map = {}
    for item in tv_data:
        ticker = item["d"][0].strip().upper()
        price = item["d"][1]
        if price is not None:
            price_map[ticker] = round(float(price), 2)

    print(f"Retrieved prices for {len(price_map)} EGX stocks.")

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
    tables = [t[0] for t in cur.fetchall()]
    table_name = next((t for t in tables if "ticker" in t.lower() or "directory" in t.lower()), tables[0])

    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s;", (table_name,))
    columns = [col[0] for col in cur.fetchall()]
    
    price_col = "current_price_egp" if "current_price_egp" in columns else next(
        (c for c in columns if "price" in c.lower() or "current" in c.lower()), None
    )

    cur.execute(f'SELECT id, ticker FROM "{table_name}" WHERE ticker IS NOT NULL;')
    db_rows = cur.fetchall()

    updates = []
    unmatched = []

    for row_id, raw_ticker in db_rows:
        ticker = raw_ticker.strip().upper()
        # Resolve alias if available, otherwise check raw symbol
        lookup_symbol = TICKER_ALIASES.get(ticker, ticker)

        if lookup_symbol in price_map:
            updates.append((price_map[lookup_symbol], row_id))
        else:
            unmatched.append(ticker)

    if updates:
        update_query = f'UPDATE "{table_name}" SET "{price_col}" = %s WHERE id = %s;'
        execute_batch(cur, update_query, updates)
        conn.commit()
        print(f"Successfully updated {len(updates)} stock prices in Glide!")

    if unmatched:
        print(f"\nUnmatched tickers ({len(unmatched)}):")
        print(", ".join(sorted(unmatched)))

    cur.close()
    conn.close()

if __name__ == "__main__":
    run_sync()
