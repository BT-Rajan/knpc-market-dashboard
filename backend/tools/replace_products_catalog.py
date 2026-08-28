"""
One-time migration: swap the "Products" catalog from the old Singapore/
regional-proxy scrape lineup to the four EIA-sourced U.S. spot price items
(Conventional Gasoline, ULSD, Jet Kerosene, Propane -- see config.SEED_CATALOG
and config.EIA_PRODUCT_SERIES).

Retired Products items are HARD DELETED (per explicit instruction), along
with their price history, news, sources, and scrape logs -- this is a
deliberate exception to this project's normal additive-only migration
style (see app/migrations.py's docstring), so there's no "undo" once it's
run. If you want the history kept instead, deactivate the items by hand
(set Item.active = False in the DB) rather than running this.

Also updates the unit label on the 4 EIA-sourced items to "$/gal" in case
this script (or seed()) already ran once before that label was corrected.

Idempotent: safe to run more than once. Run after pulling this change and
setting EIA_API_KEY in backend/.env:

    cd backend && python -m tools.replace_products_catalog
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal
from app.models import Item
from app.config import RETIRED_PRODUCT_CODES, EIA_API_KEY, SEED_CATALOG
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

    db = SessionLocal()
    try:
        # 2. Fix the unit label on the 4 new items if they were created by
        #    an earlier run of this script/seed() before it read "$/gal".
        unit_by_code = {spec["code"]: spec["unit"] for spec in SEED_CATALOG["Products"]}
        for item in db.query(Item).filter(Item.code.in_(unit_by_code)).all():
            correct_unit = unit_by_code[item.code]
            if item.unit != correct_unit:
                print(f"[OK] Fixed unit for {item.code}: '{item.unit}' -> '{correct_unit}'")
                item.unit = correct_unit
        db.commit()

        # 3. Hard-delete the retired Products items -- cascades to their
        #    sources, price history, and news (see Item.__tablename__ ==
        #    "items" cascade="all, delete-orphan" in app/models.py).
        retired = db.query(Item).filter(Item.code.in_(RETIRED_PRODUCT_CODES)).all()
        for item in retired:
            print(f"[OK] Deleted retired product: {item.code} ({item.name})")
            db.delete(item)
        if not retired:
            print("[OK] No retired-product items found (already migrated)")
        db.commit()
    finally:
        db.close()

    print("[DONE] Products catalog now contains only the 4 EIA-sourced items.")


if __name__ == "__main__":
    main()
