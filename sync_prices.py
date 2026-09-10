import os
import requests
import psycopg2
from psycopg2.extras import execute_batch

DATABASE_URL = os.getenv("DATABASE_URL")

def run_sync():
    # 1. Fetch EGX closing prices from TradingView
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

    # 2. Connect to Glide Postgres database
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Identify exact table and column names
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
          AND (table_name ILIKE '%ticker%' OR table_name ILIKE '%directory%')
        LIMIT 1;
    """)
    table_name = cur.fetchone()[0]

    cur.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = %s 
          AND (column_name ILIKE '%current_price_egp%' OR column_name ILIKE '%price%')
        LIMIT 1;
    """, (table_name,))
    
    col_row = cur.fetchone()
    price_col = col_row[0] if col_row else "current_price_egp"
    print(f"Targeting table: '{table_name}', column: '{price_col}'")

    # 3. Read tickers from Glide
    cur.execute(f'SELECT id, ticker FROM "{table_name}" WHERE ticker IS NOT NULL;')
    db_rows = cur.fetchall()

    updates = []
    for row_id, ticker in db_rows:
        sym = ticker.strip().upper()
        if sym in price_map:
            updates.append((price_map[sym], row_id))

    # 4. Commit updates
    if updates:
        update_query = f'UPDATE "{table_name}" SET "{price_col}" = %s WHERE id = %s;'
        execute_batch(cur, update_query, updates)
        conn.commit()
        print(f"Successfully updated {len(updates)} stock prices in Glide!")
    else:
        print("No matching tickers found to update.")

    cur.close()
    conn.close()

if __name__ == "__main__":
    run_sync()
