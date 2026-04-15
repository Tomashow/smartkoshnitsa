"""FastAPI application for SmartKoshnitsa."""

import os

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles

from db.models import search_products

app = FastAPI(title="SmartKoshnitsa")


@app.get("/api/search")
def search(q: str = Query(default="")):
    if not q.strip():
        return []
    return search_products(q)


# Serve extracted product images
_img_dir = "data/pdfs/images"
os.makedirs(_img_dir, exist_ok=True)
app.mount("/images", StaticFiles(directory=_img_dir), name="images")

app.mount("/", StaticFiles(directory="frontend", html=True), name="static")
