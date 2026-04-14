#!/usr/bin/env python3
"""CLI entry point for SmartKoshnitsa."""

import sys

# Fix Windows console encoding for Cyrillic
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from db.models import count_active_products, init_db


def cmd_init():
    """Initialize database, create tables, seed stores."""
    print("Initializing database...")
    init_db()
    count = count_active_products()
    print("Database initialized successfully.")
    print("  - Tables created: Store, Catalog, Product")
    print("  - Stores seeded: Kaufland, Lidl, Billa (3 stores)")
    print(f"  - Active products: {count}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python run.py <command>")
        print("Commands:")
        print("  init    - Create database and seed stores")
        sys.exit(1)

    command = sys.argv[1]

    if command == "init":
        cmd_init()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
