from datetime import date, timedelta

from app import models
from app.database import get_db
from app.deps import ensure_school_access, require_roles
from app.schemas import (
    CanteenCategoryInput,
    CanteenCategoryOut,
    CanteenCategoryPatch,
    CanteenForecastOut,
    CanteenSalesDay,
)
from app.serializers import canteen_category_out
from app.services.forecast import compute_canteen_forecast
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

router = APIRouter(tags=["canteen"])


@router.get("/schools/{school_id}/canteen/forecast", response_model=CanteenForecastOut)
def get_canteen_forecast(
    school_id: str,
    date: date,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("canteen", "school_admin")),
):
    ensure_school_access(user, school_id)
    school = db.get(models.School, school_id)
    if not school:
        raise HTTPException(status_code=404, detail="Школа не найдена")
    if school.meal_plan != "canteen":
        raise HTTPException(
            status_code=400,
            detail="Прогноз по категориям доступен только для схемы «шведский стол»",
        )
    return compute_canteen_forecast(db, school, date)


@router.get("/schools/{school_id}/canteen/sales", response_model=list[CanteenSalesDay])
def canteen_sales(
    school_id: str,
    days: int = Query(14, ge=1, le=90),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("canteen", "school_admin")),
):
    ensure_school_access(user, school_id)
    since = date.today() - timedelta(days=days)
    sales = (
        db.query(models.CanteenSale)
        .filter(
            models.CanteenSale.school_id == school_id,
            models.CanteenSale.date >= since,
        )
        .order_by(models.CanteenSale.date.asc())
        .all()
    )
    by_date: dict[date, dict] = {}
    for s in sales:
        cat = db.get(models.CanteenCategory, s.category_id)
        day = by_date.setdefault(
            s.date,
            {
                "date": s.date,
                "total_qty": 0,
                "revenue": 0.0,
                "waste_qty": 0,
                "by_category": [],
            },
        )
        day["total_qty"] += s.qty
        day["revenue"] += s.revenue
        day["waste_qty"] += s.waste_qty
        day["by_category"].append(
            {
                "id": s.category_id,
                "name": cat.name if cat else "",
                "qty": s.qty,
                "revenue": s.revenue,
                "waste_qty": s.waste_qty,
            }
        )
    return [by_date[d] for d in sorted(by_date.keys())]


@router.get("/schools/{school_id}/canteen/categories", response_model=list[CanteenCategoryOut])
def list_categories(
    school_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("canteen", "school_admin")),
):
    ensure_school_access(user, school_id)
    cats = db.query(models.CanteenCategory).filter_by(school_id=school_id).all()
    return [canteen_category_out(c) for c in cats]


@router.post(
    "/schools/{school_id}/canteen/categories",
    response_model=CanteenCategoryOut,
    status_code=201,
)
def create_category(
    school_id: str,
    payload: CanteenCategoryInput,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("canteen", "school_admin")),
):
    ensure_school_access(user, school_id)
    if not (0 <= payload.share <= 1):
        raise HTTPException(status_code=400, detail="share должен быть в диапазоне 0..1")
    cid = f"cat-{school_id}-{db.query(models.CanteenCategory).filter_by(school_id=school_id).count() + 1}"
    cat = models.CanteenCategory(
        id=cid,
        school_id=school_id,
        name=payload.name,
        share=payload.share,
        avg_price=payload.avg_price,
        unit=payload.unit,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return canteen_category_out(cat)


@router.patch("/canteen/categories/{category_id}", response_model=CanteenCategoryOut)
def patch_category(
    category_id: str,
    payload: CanteenCategoryPatch,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("canteen", "school_admin")),
):
    cat = db.get(models.CanteenCategory, category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    ensure_school_access(user, cat.school_id)
    data = payload.model_dump(exclude_unset=True)
    if "share" in data and not (0 <= data["share"] <= 1):
        raise HTTPException(status_code=400, detail="share должен быть в диапазоне 0..1")
    for k, v in data.items():
        setattr(cat, k, v)
    db.commit()
    db.refresh(cat)
    return canteen_category_out(cat)


@router.delete("/canteen/categories/{category_id}", status_code=204)
def delete_category(
    category_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("canteen", "school_admin")),
):
    cat = db.get(models.CanteenCategory, category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    ensure_school_access(user, cat.school_id)
    db.query(models.CanteenSale).filter_by(category_id=category_id).delete()
    db.delete(cat)
    db.commit()
