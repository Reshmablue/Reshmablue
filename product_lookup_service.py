"""
=============================================================================
PRODUCT LOOKUP & MULTI-TIER RECOGNITION SERVICE
AI Shopkeeper Assistant - Windows 11 & MySQL (shopkeeper_ai)
=============================================================================
Workflow:
1. Search active shop inventory ('products' table).
2. If not found, search local master catalogue ('product_catalogue' table).
3. If still missing, query official verified online APIs on demand:
   - Open Food Facts (Groceries, Packaged Foods, Beverages)
   - Open Beauty Facts (Personal Care, Cosmetics, Soaps, Shampoos)
   - Open Products Facts (Household, Stationery, General Retail Items)
4. Cache any newly identified product into 'product_catalogue' without duplicates.
5. Provide helper to register confirmed items into shop inventory ('products')
   with shop prices and stock.
=============================================================================
"""

import sys
from decimal import Decimal
from typing import Optional, Dict, Any, Tuple
import requests

# Ensure UTF-8 console output
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from catalogue_importer import classify_kirana_category


ONLINE_API_SOURCES = [
    {
        "name": "Open Food Facts (ODbL)",
        "url": "https://world.openfoodfacts.net/api/v0/product/{barcode}.json",
        "fallback_url": "https://world.openfoodfacts.org/api/v0/product/{barcode}.json",
    },
    {
        "name": "Open Beauty Facts (ODbL)",
        "url": "https://world.openbeautyfacts.org/api/v0/product/{barcode}.json",
        "fallback_url": None,
    },
    {
        "name": "Open Products Facts (ODbL)",
        "url": "https://world.openproductsfacts.org/api/v0/product/{barcode}.json",
        "fallback_url": None,
    }
]

API_HEADERS = {
    "User-Agent": "AIShopkeeperAssistant/1.0 (kirana-pos; contact@shopkeeper.local; Windows 11)"
}


def fetch_from_official_apis(barcode: str, timeout: float = 3.0) -> Optional[Dict[str, Any]]:
    """
    Look up product barcode across Open Food Facts, Open Beauty Facts,
    and Open Products Facts.
    
    Requests ONLY the necessary metadata fields. Does NOT download images.
    Returns cleaned dict on match, or None if not recognized.
    """
    clean_barcode = str(barcode).strip()
    if not clean_barcode:
        return None

    for source in ONLINE_API_SOURCES:
        endpoints = [source["url"]]
        if source.get("fallback_url"):
            endpoints.append(source["fallback_url"])

        for ep in endpoints:
            req_url = ep.format(barcode=clean_barcode)
            try:
                resp = requests.get(req_url, headers=API_HEADERS, timeout=timeout)
                if resp.status_code != 200:
                    continue

                data = resp.json()
                if data.get("status") == 1 and "product" in data:
                    p = data["product"]

                    # Extract product name
                    raw_name = (
                        p.get("product_name") or
                        p.get("product_name_en") or
                        p.get("generic_name") or
                        ""
                    ).strip()

                    if not raw_name or raw_name.lower() in ("none", "null", "unknown", "n/a"):
                        continue

                    # Extract brand
                    brand = (p.get("brands") or "").strip() or None
                    if brand and len(brand) > 150:
                        brand = brand[:147] + "..."

                    # Extract raw category and classify into 7 canonical kirana categories
                    raw_category = p.get("categories") or ""
                    category = classify_kirana_category(raw_category, raw_name)

                    # Extract package size / quantity
                    package_size = (p.get("quantity") or "").strip() or None
                    if package_size and len(package_size) > 100:
                        package_size = package_size[:100]

                    # Extract description
                    description = (p.get("generic_name") or "").strip() or None

                    # Extract image URL only (no downloading)
                    raw_img = (p.get("image_front_url") or p.get("image_url") or "").strip()
                    image_url = None
                    if raw_img.startswith("http://") or raw_img.startswith("https://"):
                        image_url = raw_img[:500]

                    return {
                        "barcode": clean_barcode,
                        "product_name": raw_name[:255],
                        "brand": brand,
                        "category": category,
                        "package_size": package_size,
                        "description": description,
                        "image_url": image_url,
                        "source": source["name"]
                    }

            except (requests.RequestException, ValueError):
                # Network timeout, DNS issue, or invalid JSON -> try next endpoint gracefully
                continue

    return None


def cache_in_catalogue(cursor, connection, item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Saves an online-identified product into 'product_catalogue' without creating duplicates.
    Returns the dictionary of the catalogue row including its catalogue_id.
    """
    barcode = str(item["barcode"]).strip()

    # Check if already present in product_catalogue
    check_sql = """
        SELECT catalogue_id, barcode, product_name, brand, category, package_size, description, image_url, source
        FROM product_catalogue
        WHERE barcode = %s
    """
    cursor.execute(check_sql, (barcode,))
    existing = cursor.fetchone()
    if existing:
        return existing

    # Insert into product_catalogue
    insert_sql = """
        INSERT INTO product_catalogue
        (barcode, product_name, brand, category, package_size, description, image_url, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    cursor.execute(
        insert_sql,
        (
            barcode,
            item["product_name"][:255],
            item["brand"][:150] if item.get("brand") else None,
            item["category"][:150] if item.get("category") else None,
            item["package_size"][:100] if item.get("package_size") else None,
            item.get("description"),
            item["image_url"][:500] if item.get("image_url") else None,
            item["source"][:100] if item.get("source") else "Open Food Facts (ODbL)"
        )
    )
    connection.commit()
    catalogue_id = cursor.lastrowid

    return {
        "catalogue_id": catalogue_id,
        "barcode": barcode,
        "product_name": item["product_name"],
        "brand": item.get("brand"),
        "category": item.get("category"),
        "package_size": item.get("package_size"),
        "description": item.get("description"),
        "image_url": item.get("image_url"),
        "source": item.get("source")
    }


def lookup_product_tiered(cursor, connection, barcode: str, allow_online: bool = True) -> Dict[str, Any]:
    """
    Executes the 3-tier lookup workflow:
    Tier 1: Search 'products' table using exact scanned barcode.
    Tier 2: If not in products, search 'product_catalogue'.
    Tier 3: If still missing, query official online APIs (Open Food Facts, Open Beauty Facts, Open Products Facts).
            If found online, cache in 'product_catalogue' immediately.
            
    Returns:
      {
        "status": "FOUND_IN_INVENTORY" | "FOUND_IN_CATALOGUE" | "FOUND_ONLINE" | "NOT_FOUND",
        "tier": 1 | 2 | 3 | 0,
        "product": dict or None (inventory record with price & stock),
        "catalogue_item": dict or None (catalogue record with name, brand, category),
        "barcode": str,
        "message": str
      }
    """
    clean_barcode = str(barcode).strip()
    if not clean_barcode:
        return {
            "status": "NOT_FOUND",
            "tier": 0,
            "product": None,
            "catalogue_item": None,
            "barcode": "",
            "message": "Empty barcode provided."
        }

    # =========================================================================
    # TIER 1: Search active shop inventory ('products' table)
    # =========================================================================
    inv_sql = """
        SELECT
            product_id,
            product_name,
            category,
            unit,
            selling_price,
            purchase_price,
            current_stock,
            reorder_level,
            barcode,
            is_active,
            catalogue_id
        FROM products
        WHERE barcode = %s
          AND is_active = 1
    """
    cursor.execute(inv_sql, (clean_barcode,))
    inv_product = cursor.fetchone()

    if inv_product:
        return {
            "status": "FOUND_IN_INVENTORY",
            "tier": 1,
            "product": inv_product,
            "catalogue_item": None,
            "barcode": clean_barcode,
            "message": f"Found in store inventory: '{inv_product['product_name']}'."
        }

    # =========================================================================
    # TIER 2: Search master catalogue ('product_catalogue' table)
    # =========================================================================
    cat_sql = """
        SELECT
            catalogue_id,
            barcode,
            product_name,
            brand,
            category,
            package_size,
            description,
            image_url,
            source
        FROM product_catalogue
        WHERE barcode = %s
    """
    cursor.execute(cat_sql, (clean_barcode,))
    cat_item = cursor.fetchone()

    if cat_item:
        return {
            "status": "FOUND_IN_CATALOGUE",
            "tier": 2,
            "product": None,
            "catalogue_item": cat_item,
            "barcode": clean_barcode,
            "message": f"Found in local master catalogue: '{cat_item['product_name']}' ({cat_item.get('brand') or 'N/A'})."
        }

    # =========================================================================
    # TIER 3: Query official online product APIs (on demand, no bulk download)
    # =========================================================================
    if allow_online:
        online_data = fetch_from_official_apis(clean_barcode, timeout=3.5)
        if online_data:
            # Cache immediately in product_catalogue without duplicates
            cached_cat = cache_in_catalogue(cursor, connection, online_data)
            return {
                "status": "FOUND_ONLINE",
                "tier": 3,
                "product": None,
                "catalogue_item": cached_cat,
                "barcode": clean_barcode,
                "online_source": online_data["source"],
                "message": (
                    f"Recognised via {online_data['source']}: '{online_data['product_name']}' "
                    f"({online_data.get('brand') or 'Brand N/A'}) and cached in local catalogue."
                )
            }

    # =========================================================================
    # NOT FOUND ANYWHERE: Offer manual registration
    # =========================================================================
    return {
        "status": "NOT_FOUND",
        "tier": 0,
        "product": None,
        "catalogue_item": None,
        "barcode": clean_barcode,
        "message": f"Barcode '{clean_barcode}' not found in inventory, catalogue, or official online databases."
    }


def register_product_to_inventory(
    cursor,
    connection,
    product_name: str,
    selling_price: Decimal,
    category: str = "General",
    unit: str = "piece",
    purchase_price: Decimal = Decimal("0.00"),
    current_stock: Decimal = Decimal("10.00"),
    reorder_level: Decimal = Decimal("5.00"),
    barcode: Optional[str] = None,
    catalogue_id: Optional[int] = None
) -> int:
    """
    Safely adds a product to shop inventory ('products' table) only after shopkeeper confirmation
    with verified selling price, purchase cost, and stock quantities.
    Returns the newly created product_id.
    """
    clean_barcode = str(barcode).strip() if barcode else None

    # Verification: Validate positive selling price
    if selling_price <= Decimal("0"):
        raise ValueError("Selling price must be greater than zero.")
    if purchase_price < Decimal("0"):
        raise ValueError("Purchase price cannot be negative.")
    if current_stock < Decimal("0"):
        raise ValueError("Stock quantity cannot be negative.")

    insert_sql = """
        INSERT INTO products 
        (product_name, category, unit, selling_price, purchase_price, current_stock, reorder_level, barcode, is_active, catalogue_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, %s)
    """
    cursor.execute(
        insert_sql,
        (
            product_name[:150],
            category[:100],
            unit[:30],
            selling_price,
            purchase_price,
            current_stock,
            reorder_level,
            clean_barcode,
            catalogue_id
        )
    )
    connection.commit()
    return cursor.lastrowid
