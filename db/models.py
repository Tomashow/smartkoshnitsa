"""Database models and functions for SmartKoshnitsa."""

import os
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv
from rapidfuzz import fuzz
from sqlmodel import Field, Session, SQLModel, create_engine, select

load_dotenv()

# --- Models ---


class Store(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    slug: str = Field(unique=True, index=True)
    website_url: str | None = None
    logo_url: str | None = None


class Catalog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    store_id: int = Field(foreign_key="store.id", index=True)
    start_date: date
    end_date: date
    source_url: str
    scraped_at: datetime = Field(default_factory=datetime.utcnow)


class Product(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    catalog_id: int = Field(foreign_key="catalog.id", index=True)
    name: str = Field(index=True)
    price: float
    original_price: float | None = None
    unit: str | None = None
    quantity: float | None = None
    image_url: str | None = None
    scraped_at: datetime = Field(default_factory=datetime.utcnow)


# --- Engine ---

_engine = None


def get_engine():
    """Get or create database engine. Reads DB_PATH from env, defaults to data/smartkoshnitsa.db."""
    global _engine
    if _engine is None:
        db_path = os.getenv("DB_PATH", "data/smartkoshnitsa.db")
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
    return _engine


# --- Functions ---


def init_db() -> None:
    """Create all tables and seed stores if not exist."""
    engine = get_engine()
    SQLModel.metadata.create_all(engine)

    stores = [
        Store(name="Кауфланд", slug="kaufland", website_url="https://www.kaufland.bg"),
        Store(name="Лидл", slug="lidl", website_url="https://www.lidl.bg"),
        Store(name="Билла", slug="billa", website_url="https://www.billa.bg"),
    ]

    with Session(engine) as session:
        for store in stores:
            existing = session.exec(
                select(Store).where(Store.slug == store.slug)
            ).first()
            if not existing:
                session.add(store)
        session.commit()


def get_or_create_catalog(
    store_slug: str,
    start_date: date,
    end_date: date,
    source_url: str,
) -> int:
    """Get existing or create new Catalog for a store. Returns catalog id."""
    engine = get_engine()
    with Session(engine) as session:
        store = session.exec(select(Store).where(Store.slug == store_slug)).first()
        if not store:
            raise ValueError(f"Store not found: {store_slug}")
        existing = session.exec(
            select(Catalog).where(
                Catalog.store_id == store.id,
                Catalog.start_date == start_date,
                Catalog.end_date == end_date,
            )
        ).first()
        if existing:
            return existing.id
        catalog = Catalog(
            store_id=store.id,
            start_date=start_date,
            end_date=end_date,
            source_url=source_url,
        )
        session.add(catalog)
        session.commit()
        session.refresh(catalog)
        return catalog.id


def upsert_products(products: list[dict]) -> int:
    """Insert products into database. Returns count of inserted products."""
    engine = get_engine()
    count = 0
    with Session(engine) as session:
        for prod_data in products:
            product = Product(**prod_data)
            session.add(product)
            count += 1
        session.commit()
    return count


def search_products(query: str, limit: int = 50) -> list[dict]:
    """Fuzzy search products by name. Returns list of product dicts with store info."""
    engine = get_engine()
    threshold = 65

    with Session(engine) as session:
        # Get all active products (from catalogs that haven't expired)
        today = date.today()
        results = session.exec(
            select(Product, Catalog, Store)
            .join(Catalog, Product.catalog_id == Catalog.id)
            .join(Store, Catalog.store_id == Store.id)
            .where(Catalog.end_date >= today)
        ).all()

        # Fuzzy match and score
        scored = []
        for product, catalog, store in results:
            score = fuzz.WRatio(query.lower(), product.name.lower())
            if score >= threshold:
                scored.append((score, product, catalog, store))

        # Sort by score descending, take top N
        scored.sort(key=lambda x: x[0], reverse=True)
        scored = scored[:limit]

        return [
            {
                "id": product.id,
                "name": product.name,
                "price": product.price,
                "original_price": product.original_price,
                "unit": product.unit,
                "quantity": product.quantity,
                "image_url": product.image_url,
                "store_name": store.name,
                "store_slug": store.slug,
                "valid_from": catalog.start_date.strftime("%d.%m"),
                "valid_to": catalog.end_date.strftime("%d.%m"),
                "score": score,
            }
            for score, product, catalog, store in scored
        ]


def get_basket_comparison(item_queries: list[str]) -> dict:
    """Compare prices across stores for a list of items.

    Returns dict with:
        - items: list of {query, matches: {store_slug: best_match}}
        - totals: {store_slug: total_price}
    """
    engine = get_engine()
    threshold = 65
    today = date.today()

    with Session(engine) as session:
        # Get all stores
        stores = session.exec(select(Store)).all()
        store_map = {s.id: s for s in stores}

        # Get all active products grouped by store
        results = session.exec(
            select(Product, Catalog)
            .join(Catalog, Product.catalog_id == Catalog.id)
            .where(Catalog.end_date >= today)
        ).all()

        # Group products by store_id
        products_by_store: dict[int, list[Product]] = {}
        for product, catalog in results:
            if catalog.store_id not in products_by_store:
                products_by_store[catalog.store_id] = []
            products_by_store[catalog.store_id].append(product)

        items = []
        totals = {s.slug: 0.0 for s in stores}

        for query in item_queries:
            matches = {}
            for store_id, products in products_by_store.items():
                store = store_map[store_id]
                best_match = None
                best_score = 0

                for product in products:
                    score = fuzz.WRatio(query.lower(), product.name.lower())
                    if score >= threshold and score > best_score:
                        best_score = score
                        best_match = {
                            "id": product.id,
                            "name": product.name,
                            "price": product.price,
                            "original_price": product.original_price,
                            "score": score,
                        }

                if best_match:
                    matches[store.slug] = best_match
                    totals[store.slug] += best_match["price"]

            items.append({"query": query, "matches": matches})

        return {"items": items, "totals": totals}


def count_active_products() -> int:
    """Count products from active catalogs (end_date >= today)."""
    engine = get_engine()
    today = date.today()

    with Session(engine) as session:
        count = len(
            session.exec(
                select(Product)
                .join(Catalog, Product.catalog_id == Catalog.id)
                .where(Catalog.end_date >= today)
            ).all()
        )
    return count
