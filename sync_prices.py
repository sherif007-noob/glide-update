import os
import psycopg2
from psycopg2.extras import execute_batch
import yfinance as yf

DATABASE_URL = os.getenv("DATABASE_URL")

def run_sync():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Locate table name dynamically
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
    print(f"Updating table: {table_name}")

    cur.execute(f'SELECT id, ticker FROM "{table_name}" WHERE ticker IS NOT NULL;')
    rows = cur.fetchall()
    if not rows:
        return

    ticker_map = {r[1].strip(): r[0] for r in rows if r[1]}
    yf_symbols = [f"{t}.CA" for t in ticker_map.keys()]

    market_data = yf.download(yf_symbols, period="1d", interval="1d", group_by="ticker", progress=False)

    updates = []
    for ticker, row_id in ticker_map.items():
        sym = f"{ticker}.CA"
        try:
            if len(ticker_map) == 1:
                price = market_data["Close"].iloc[-1]
            else:
                price = market_data[sym]["Close"].iloc[-1]

            if price is not None and str(price) != "nan":
                updates.append((round(float(price), 2), row_id))
        except Exception as e:
            print(f"Skipping {ticker}: {e}")

    update_query = f'UPDATE "{table_name}" SET current_price = %s WHERE id = %s;'
    execute_batch(cur, update_query, updates)
    conn.commit()

    cur.close()
    conn.close()
    print(f"Updated {len(updates)} records.")

if __name__ == "__main__":
    run_sync()
