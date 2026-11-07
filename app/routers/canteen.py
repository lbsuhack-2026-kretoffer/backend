from datetime import timedelta

from fastapi import APIRouter, HTTPException

from ..deps import DB, CurrentUser, ensure_school_access
from ..models import (
    CanteenCategory,
    CanteenSale,
    School,
)
from ..schemas import CanteenCategoryInput, CanteenCategoryPatch
from ..utils import parse_date, today_tz
from .forecast import _build_forecast

router = APIRouter(tags=["canteen"])


@router.get("/schools/{school_id}/canteen/categories")
def list_categories(school_id: str, db: DB, user: CurrentUser):
    ensure_school_access(user, school_id)
    items = db.query(CanteenCategory).filter(CanteenCategory.school_id == school_id).all()
    return [
        {
            "id": c.id,
            "schoolId": c.school_id,
            "name": c.name,
            "share": c.share,
            "avgPrice": c.avg_price,
            "unit": c.unit,
        }
        for c in items
    ]


@router.post("/schools/{school_id}/canteen/categories", status_code=201)
def create_category(school_id: str, data: CanteenCategoryInput, db: DB, user: CurrentUser):
    ensure_school_access(user, school_id)
    if user.role not in ("platform_admin", "school_admin", "canteen"):
        raise HTTPException(403, "Недостаточно прав")
    c = CanteenCategory(
        school_id=school_id,
        name=data.name,
        share=data.share,
        avg_price=data.avgPrice,
        unit=data.unit,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return {
        "id": c.id,
        "schoolId": c.school_id,
        "name": c.name,
        "share": c.share,
        "avgPrice": c.avg_price,
        "unit": c.unit,
    }


@router.patch("/canteen/categories/{category_id}")
def patch_category(category_id: str, data: CanteenCategoryPatch, db: DB, user: CurrentUser):
    c = db.get(CanteenCategory, category_id)
    if not c:
        raise HTTPException(404, "Категория не найдена")
    ensure_school_access(user, c.school_id)
    if user.role not in ("platform_admin", "school_admin", "canteen"):
        raise HTTPException(403, "Недостаточно прав")
    payload = data.model_dump(exclude_unset=True)
    if "name" in payload and payload["name"] is not None:
        c.name = payload["name"]
    if "share" in payload and payload["share"] is not None:
        c.share = payload["share"]
    if "avgPrice" in payload and payload["avgPrice"] is not None:
        c.avg_price = payload["avgPrice"]
    if "unit" in payload and payload["unit"] is not None:
        c.unit = payload["unit"]
    db.commit()
    db.refresh(c)
    return {
        "id": c.id,
        "schoolId": c.school_id,
        "name": c.name,
        "share": c.share,
        "avgPrice": c.avg_price,
        "unit": c.unit,
    }


@router.delete("/canteen/categories/{category_id}", status_code=204)
def delete_category(category_id: str, db: DB, user: CurrentUser):
    c = db.get(CanteenCategory, category_id)
    if not c:
        raise HTTPException(404, "Категория не найдена")
    ensure_school_access(user, c.school_id)
    if user.role not in ("platform_admin", "school_admin", "canteen"):
        raise HTTPException(403, "Недостаточно прав")
    db.delete(c)
    db.commit()
    return None


@router.get("/schools/{school_id}/canteen/forecast")
def canteen_forecast(school_id: str, db: DB, user: CurrentUser, date: str | None = None):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(404, "Школа не найдена")
    ensure_school_access(user, school_id)
    target = parse_date(date)
    f = _build_forecast(db, school, target)
    return {
        "schoolId": school.id,
        "schoolName": school.name,
        "date": target.isoformat(),
        "mealPlan": school.meal_plan,
        "present": f["present"],
        "byCategory": f["byCategory"],
        "totalPortions": f["totalPortions"],
        "adjustmentDelta": f["adjustmentDelta"],
        "status": f["status"],
        "approvedAt": f["approvedAt"],
        "approvedBy": f["approvedBy"],
        "comment": f["comment"],
        "basedOnDate": f["basedOnDate"],
        "markedClasses": f["markedClasses"],
        "totalClasses": f["totalClasses"],
        "mlCategories": f.get("mlCategories"),
        "mlModelUsed": f.get("mlModelUsed"),
    }


@router.get("/schools/{school_id}/canteen/sales")
def canteen_sales(school_id: str, db: DB, user: CurrentUser, days: int = 14):
    ensure_school_access(user, school_id)
    end = today_tz()
    start = end - timedelta(days=days - 1)
    sales = (
        db.query(CanteenSale)
        .filter(
            CanteenSale.school_id == school_id, CanteenSale.date >= start, CanteenSale.date <= end
        )
        .all()
    )
    cats = {
        c.id: c
        for c in db.query(CanteenCategory).filter(CanteenCategory.school_id == school_id).all()
    }
    by_day: dict[str, dict] = {}
    for s in sales:
        d = s.date.isoformat()
        bucket = by_day.setdefault(d, {"date": d, "qty": 0, "amount": 0.0, "categories": {}})
        bucket["qty"] += s.qty
        bucket["amount"] += s.amount
        if s.category_id and s.category_id in cats:
            cat = cats[s.category_id]
            cb = bucket["categories"].setdefault(
                cat.id,
                {
                    "id": cat.id,
                    "name": cat.name,
                    "qty": 0,
                    "amount": 0.0,
                },
            )
            cb["qty"] += s.qty
            cb["amount"] += s.amount
    result = []
    d = start
    while d <= end:
        key = d.isoformat()
        row = by_day.get(key, {"date": key, "qty": 0, "amount": 0.0, "categories": {}})
        row["categories"] = list(row["categories"].values())
        result.append(row)
        d += timedelta(days=1)
    return result
