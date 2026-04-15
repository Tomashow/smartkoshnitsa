The $ARGUMENTS scraper needs fixing.

1. First show me current output:
   python3 -c "
   import asyncio
   from scrapers.$ARGUMENTS import $(python3 -c "print('$ARGUMENTS'.title()")Scraper
   async def t():
   s = $(python3 -c "print('$ARGUMENTS'.title()")Scraper()
   p = await s.scrape()
   print(f'Current count: {len(p)}')
   if p: print('Sample:', p[0])
   asyncio.run(t())
   "

2. Inspect the target page fresh
3. Compare selectors in code vs what page actually has now
4. Fix the mismatch
5. Test again — must return 100+ products
6. Run tests: python3 -m pytest tests/ -v
