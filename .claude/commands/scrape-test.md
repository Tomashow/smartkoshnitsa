Test the $ARGUMENTS scraper end to end.

Steps:

1. Run: python3 -c "import asyncio; from scrapers.$ARGUMENTS import $(echo $ARGUMENTS | sed 's/./\u&/')Scraper; asyncio.run($ARGUMENTS_capitalized().scrape())"
2. Print first 5 products found
3. Print total count
4. If 0 products: diagnose why, check selectors
5. If products found: run upsert and confirm DB count increased
