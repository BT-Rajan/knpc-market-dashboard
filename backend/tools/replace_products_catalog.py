"""
One-time migration: swap the "Products" catalog from the old Singapore/
regional-proxy scrape lineup to the four EIA-sourced U.S. spot price items
(Conventional Gasoline, ULSD, Jet Kerosene, Propane -- see config.SEED_CATALOG
and config.EIA_PRODUCT_SERIES).

Non-destructive, matching this project's migration style (see
app/migrations.py's docstring): old product items are deactivated, not
deleted, so their price/news history stays in the DB and nothing breaks if
you need to look back at it. Deactivated items drop out of the nav, ticker,
and quarterly report automatically (every query filters on Item.active).

Idempotent: safe to run more than once. Run after pulling this change and
setting EIA_API_KEY in backend/.env:

    cd backend && python -m tools.replace_products_catalog
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal
from app.models import Item
from app.config import RETIRED_PRODUCT_CODES, EIA_API_KEY
from app.seed import seed


def main():
    if not EIA_API_KEY:
        print(
            "[WARN] EIA_API_KEY is not set in backend/.env -- the new Products "
            "items will be created, but price collection will fail until you "
            "add a free key from https://www.eia.gov/opendata/register.php"
        )

    # 1. Insert the new EIA-sourced Products items + sources (idempotent --
    #    only fills in what's missing, matches app/seed.py's own contract).
    seed()

    # 2. Deactivate the retired Products items so they disappear from the
    #    nav/ticker/reports without losing their history.
    db = SessionLocal()
    try:
        retired = (
            db.query(Item)
            .filter(Item.code.in_(RETIRED_PRODUCT_CODES), Item.active == True)  # noqa: E712
            .all()
        )
        for item in retired:
            item.active = False
            print(f"[OK] Deactivated retired product: {item.code} ({item.name})")
        if not retired:
            print("[OK] No active retired-product items found (already migrated)")
        db.commit()
    finally:
        db.close()

    print("[DONE] Products catalog now points at the EIA daily spot-price set.")


if __name__ == "__main__":
    main()
