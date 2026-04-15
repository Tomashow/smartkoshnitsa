Give me a project status report:

1. Run tests: python3 -m pytest tests/ -v
2. Count products per store:
   python3 -c "
   from db.models import get_engine
   from sqlmodel import Session, text
   with Session(get_engine()) as s:
   rows = s.exec(text('SELECT st.name, COUNT(p.id) as cnt FROM product p JOIN catalog c ON p.catalog_id=c.id JOIN store st ON c.store_id=st.id GROUP BY st.name')).all()
   for r in rows: print(f'{r[0]}: {r[1]} products')
   "
3. Show what is in CLAUDE.md current focus section
4. Tell me what the next task is
