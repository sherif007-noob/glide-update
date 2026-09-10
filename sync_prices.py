import os
import requests
import psycopg2
from psycopg2.extras import execute_batch

DATABASE_URL = os.getenv("DATABASE_URL")

def run_sync():
    # 1. Fetch Egyptian Exchange closing prices via TradingView Scanner
    print("Fetching EGX closing prices...")
    tv_url = "https://scanner.tradingview.com/egypt/scan"
    payload = {
        "filter": [],
        "options": {"lang": "en"},
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": ["name", "close"],
        "sort": {"sortBy": "name", "sortOrder": "asc"},
        "range": [0, 400]
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    response = requests.post(tv_url, json=payload, headers=headers, timeout=20)
    response.raise_for_status()
    tv_data = response.json().get("data", [])

    price_map = {}
    for item in tv_data:
        ticker = item["d"][0].strip().upper()
        price = item["d"][1]
        if price is not None:
            price_map[ticker] = round(float(price), 2)

    print(f"Retrieved prices for {len(price_map)} EGX stocks.")

    # 2. Connect to database
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
          AND (table_name ILIKE '%ticker%' OR table_name ILIKE '%directory%')
        LIMIT 1;
    """)
    row = cur.fetchone()
    if not row:
        print("Table not found.")
        return

    table_name = row[0]
    print(f"Connected to table: {table_name}")

    cur.execute(f'SELECT id, ticker FROM "{table_name}" WHERE ticker IS NOT NULL;')
    db_rows = cur.fetchall()

    updates = []
    for row_id, ticker in db_rows:
        sym = ticker.strip().upper()
        if sym in price_map:
            updates.append((price_map[sym], row_id))
        else:
            print(f"No price found for ticker: {sym}")

    if updates:
        update_query = f'UPDATE "{table_name}" SET current_price = %s WHERE id = %s;'
        execute_batch(cur, update_query, updates)
        conn.commit()

    cur.close()
    conn.close()
    print(f"Successfully updated {len(updates)} records in Glide!")

if __name__ == "__main__":
    run_sync()
