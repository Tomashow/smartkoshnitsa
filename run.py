#!/usr/bin/env python3
"""CLI entry point for SmartKoshnitsa."""

import sys

# Fix Windows console encoding for Cyrillic
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from db.models import count_active_products, init_db, search_products, upsert_products


def cmd_init():
    """Initialize database, create tables, seed stores."""
    print("Initializing database...")
    init_db()
    count = count_active_products()
    print("Database initialized successfully.")
    print("  - Tables created: Store, Catalog, Product")
    print("  - Stores seeded: Kaufland, Lidl, Billa (3 stores)")
    print(f"  - Active products: {count}")


def cmd_scrape():
    """Run all scrapers and insert products into the database."""
    from scrapers.billa import BillaScraper

    scraper = BillaScraper()
    products = scraper.scrape()
    if products:
        count = upsert_products(products)
        print(f"Inserted {count} products.")
    total = count_active_products()
    print(f"Total active products in DB: {total}")


def cmd_serve():
    """Start the FastAPI server (port from $PORT env var, default 8000)."""
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, reload=False)


def cmd_search(query: str):
    """Fuzzy search products by name."""
    results = search_products(query)
    if not results:
        print(f"No results for: {query!r}")
        return
    for r in results:
        orig = f" (було {r['original_price']:.2f})" if r["original_price"] else ""
        print(f"[{r['store_name']}] {r['name']} — {r['price']:.2f} лв.{orig} ({r['score']:.0f}%)")


def main():
    if len(sys.argv) < 2:
        print("Usage: python run.py <command>")
        print("Commands:")
        print("  init          - Create database and seed stores")
        print("  scrape        - Run all scrapers")
        print("  serve         - Start web UI on http://localhost:8000")
        print("  search <term> - Search products")
        sys.exit(1)

    command = sys.argv[1]

    if command == "init":
        cmd_init()
    elif command == "scrape":
        cmd_scrape()
    elif command == "serve":
        cmd_serve()
    elif command == "search":
        if len(sys.argv) < 3:
            print("Usage: python run.py search <query>")
            sys.exit(1)
        cmd_search(sys.argv[2])
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
