"""FastAPI application for SmartKoshnitsa."""

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles

from db.models import search_products

app = FastAPI(title="SmartKoshnitsa")


@app.get("/api/search")
def search(q: str = Query(default="")):
    if not q.strip():
        return []
    return search_products(q)


app.mount("/", StaticFiles(directory="frontend", html=True), name="static")
