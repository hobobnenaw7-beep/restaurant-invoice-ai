"""
Product Identity API Routes
============================
CRUD + resolution for the Universal Product Identity Layer.
"""
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone

from core.database import db
from core.auth import get_user
from services.audit import audit_log
from services.product_identity import (
    resolve_product_identity,
    create_canonical_product,
    create_vendor_mapping,
    create_alias,
    generate_initial_products,
    normalize_product_text,
    extract_keywords,
    extract_attributes,
    compute_keyword_similarity,
)

router = APIRouter()


@router.get("/products/canonical")
async def list_canonical_products(user=Depends(get_user), search: str = "", status: str = ""):
    """List all canonical products."""
    query = {"restaurant_id": user["restaurant_id"]}
    if search:
        query["canonical_name"] = {"$regex": search, "$options": "i"}
    if status:
        query["status"] = status
    products = await db.canonical_products.find(query, {"_id": 0}).sort("canonical_name", 1).to_list(500)

    # Enrich with mapping counts
    for p in products:
        p["vendor_mapping_count"] = await db.vendor_product_mappings.count_documents(
            {"canonical_product_id": p["id"], "restaurant_id": user["restaurant_id"]}
        )
        p["alias_count"] = await db.product_aliases.count_documents(
            {"canonical_product_id": p["id"], "restaurant_id": user["restaurant_id"]}
        )
    return products


@router.post("/products/canonical")
async def create_product(body: dict, user=Depends(get_user)):
    """Create a new canonical product."""
    name = (body.get("canonical_name") or "").strip()
    if not name:
        raise HTTPException(400, "canonical_name is required")

    product = await create_canonical_product(
        db, user["restaurant_id"],
        canonical_name=name,
        category=body.get("category", ""),
        attributes=body.get("attributes", {}),
        source="manual",
    )
    return product


@router.get("/products/canonical/{pid}")
async def get_product(pid: str, user=Depends(get_user)):
    """Get a canonical product with its vendor mappings and aliases."""
    product = await db.canonical_products.find_one(
        {"id": pid, "restaurant_id": user["restaurant_id"]}, {"_id": 0}
    )
    if not product:
        raise HTTPException(404, "Product not found")

    product["vendor_mappings"] = await db.vendor_product_mappings.find(
        {"canonical_product_id": pid, "restaurant_id": user["restaurant_id"]}, {"_id": 0}
    ).to_list(100)

    product["aliases"] = await db.product_aliases.find(
        {"canonical_product_id": pid, "restaurant_id": user["restaurant_id"]}, {"_id": 0}
    ).to_list(100)

    return product


@router.post("/products/canonical/{pid}/vendor-mapping")
async def add_vendor_mapping(pid: str, body: dict, user=Depends(get_user)):
    """Map a vendor+code to a canonical product."""
    product = await db.canonical_products.find_one(
        {"id": pid, "restaurant_id": user["restaurant_id"]}, {"_id": 0}
    )
    if not product:
        raise HTTPException(404, "Product not found")

    vendor_key = (body.get("vendor_key") or "").strip().upper()
    product_code = (body.get("product_code") or "").strip()
    if not vendor_key or not product_code:
        raise HTTPException(400, "vendor_key and product_code are required")

    mapping = await create_vendor_mapping(
        db, user["restaurant_id"],
        vendor_key=vendor_key,
        product_code=product_code,
        canonical_product_id=pid,
        vendor_description=body.get("vendor_description", ""),
        pack_size=body.get("pack_size", ""),
        source="user_corrected",
        user_id=user["id"],
        user_name=user.get("name", ""),
    )
    return mapping


@router.post("/products/canonical/{pid}/alias")
async def add_alias(pid: str, body: dict, user=Depends(get_user)):
    """Add a text alias to a canonical product."""
    product = await db.canonical_products.find_one(
        {"id": pid, "restaurant_id": user["restaurant_id"]}, {"_id": 0}
    )
    if not product:
        raise HTTPException(404, "Product not found")

    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text is required")

    normalized = normalize_product_text(text)
    alias_doc = await create_alias(
        db, user["restaurant_id"],
        normalized_text=normalized,
        canonical_product_id=pid,
        confidence=1.0,
        source="user_corrected",
        user_id=user["id"],
    )
    return alias_doc


@router.post("/products/resolve")
async def resolve_product(body: dict, user=Depends(get_user)):
    """Resolve a raw item name to a canonical product."""
    raw_name = (body.get("raw_name") or "").strip()
    vendor_key = (body.get("vendor_key") or "").strip().upper()
    product_code = (body.get("product_code") or "").strip()

    if not raw_name:
        raise HTTPException(400, "raw_name is required")

    result = await resolve_product_identity(
        db, user["restaurant_id"],
        raw_name=raw_name,
        vendor_key=vendor_key,
        product_code=product_code,
    )
    return result


@router.post("/products/generate-initial")
async def generate_initial(user=Depends(get_user)):
    """Generate initial canonical product list from existing data."""
    result = await generate_initial_products(db, user["restaurant_id"])
    return result


@router.post("/products/confirm-link")
async def confirm_link(body: dict, user=Depends(get_user)):
    """
    User confirms that a vendor item IS the same as a canonical product.
    Creates both a vendor mapping and a text alias with source=user_corrected.
    """
    canonical_product_id = (body.get("canonical_product_id") or "").strip()
    raw_name = (body.get("raw_name") or "").strip()
    vendor_key = (body.get("vendor_key") or "").strip().upper()
    product_code = (body.get("product_code") or "").strip()

    if not canonical_product_id:
        raise HTTPException(400, "canonical_product_id is required")

    product = await db.canonical_products.find_one(
        {"id": canonical_product_id, "restaurant_id": user["restaurant_id"]}, {"_id": 0}
    )
    if not product:
        raise HTTPException(404, "Canonical product not found")

    # Create vendor mapping if code provided
    if vendor_key and product_code:
        await create_vendor_mapping(
            db, user["restaurant_id"],
            vendor_key=vendor_key,
            product_code=product_code,
            canonical_product_id=canonical_product_id,
            vendor_description=raw_name,
            source="user_corrected",
            user_id=user["id"],
            user_name=user.get("name", ""),
        )

    # Create text alias
    if raw_name:
        norm = normalize_product_text(raw_name)
        await create_alias(
            db, user["restaurant_id"],
            normalized_text=norm,
            canonical_product_id=canonical_product_id,
            confidence=1.0,
            source="user_corrected",
            user_id=user["id"],
        )

    await audit_log(
        user, "LINK", "Product", canonical_product_id,
        f'{user["name"]} confirmed {raw_name[:40]} ({vendor_key}:{product_code}) = {product["canonical_name"]}',
    )

    return {"status": "linked", "canonical_product_id": canonical_product_id, "canonical_name": product["canonical_name"]}
