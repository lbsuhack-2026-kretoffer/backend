from fastapi import APIRouter, Depends, HTTPException

from ..deps import DB, CurrentUser, require_roles
from ..models import CanteenKitchen, CanteenMenuItem, School, User
from ..schemas import KitchenOut, MenuItemInput, MenuItemOut, SchoolOut, UserOut
from .platform import school_to_out

router = APIRouter(
    prefix="/kitchen",
    tags=["kitchen"],
    dependencies=[Depends(require_roles("canteen", "platform_admin"))],
)


def user_to_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        fullName=user.full_name,
        email=user.email,
        role=user.role,
        schoolId=user.school_id,
        schoolName=None,
        district=user.district,
        position=user.position,
        avatarUrl=user.avatar_url,
    )


@router.get("/me", response_model=UserOut)
def get_me(user: CurrentUser):
    return user_to_out(user)


@router.get("/kitchens", response_model=list[KitchenOut])
def list_my_kitchens(db: DB, user: CurrentUser):
    kitchens = db.query(CanteenKitchen).all()
    return [{"id": k.id, "name": k.name, "district": k.district} for k in kitchens]


@router.get("/kitchens/{kitchen_id}/menu", response_model=list[MenuItemOut])
def get_kitchen_menu(kitchen_id: str, db: DB):
    items = db.query(CanteenMenuItem).filter(CanteenMenuItem.kitchen_id == kitchen_id).all()
    return [
        {"id": i.id, "kitchen_id": i.kitchen_id, "name": i.name, "price": i.price}
        for i in items
    ]


@router.get("/kitchens/{kitchen_id}/schools", response_model=list[SchoolOut])
def list_kitchen_schools(kitchen_id: str, db: DB, user: CurrentUser):
    kitchen = db.get(CanteenKitchen, kitchen_id)
    if not kitchen:
        raise HTTPException(404, "КШП не найдено")
    if user.role == "canteen" and user.district != kitchen.district:
        raise HTTPException(403, "Доступ к чужому району запрещён")
    schools = db.query(School).filter(School.kitchen_id == kitchen_id).all()
    return [school_to_out(s, db) for s in schools]


@router.get("/schools", response_model=list[SchoolOut])
def list_schools_by_district(
    db: DB,
    user: CurrentUser,
    district: str | None = None,
    mealPlan: str | None = None,
):
    """Список школ района с фильтром по типу питания (для кабинета КШП)."""
    target_district = district or user.district
    if not target_district:
        raise HTTPException(400, "Не указан район")
    q = db.query(School).filter(School.district == target_district)
    if mealPlan:
        q = q.filter(School.meal_plan == mealPlan)
    schools = q.order_by(School.name).all()
    return [school_to_out(s, db) for s in schools]


@router.post(
    "/kitchens/{kitchen_id}/menu", response_model=MenuItemOut, status_code=201
)
def create_kitchen_menu_item(
    kitchen_id: str, data: MenuItemInput, db: DB, user: CurrentUser
):
    item = CanteenMenuItem(kitchen_id=kitchen_id, name=data.name, price=data.price)
    db.add(item)
    db.commit()
    db.refresh(item)
    return {
        "id": item.id,
        "kitchen_id": item.kitchen_id,
        "name": item.name,
        "price": item.price,
    }


@router.delete("/kitchens/{kitchen_id}/menu/{item_id}", status_code=204)
def delete_kitchen_menu_item(kitchen_id: str, item_id: str, db: DB):
    item = (
        db.query(CanteenMenuItem)
        .filter(CanteenMenuItem.id == item_id, CanteenMenuItem.kitchen_id == kitchen_id)
        .first()
    )
    if not item:
        raise HTTPException(404, "Блюдо не найдено")
    db.delete(item)
    db.commit()
    return None


# Школа видит меню своего КШП
@router.get("/schools/{school_id}/kitchen/menu", response_model=list[MenuItemOut])
def get_school_kitchen_menu(school_id: str, db: DB, user: CurrentUser):
    if user.role not in ("platform_admin", "school_admin", "canteen"):
        raise HTTPException(403, "Недостаточно прав")
    if user.role == "school_admin" and user.school_id != school_id:
        raise HTTPException(403, "Доступ к чужой школе запрещён")

    school = db.get(School, school_id)
    if not school:
        raise HTTPException(404, "Школа не найдена")
    if not school.kitchen_id:
        return []

    items = (
        db.query(CanteenMenuItem)
        .filter(CanteenMenuItem.kitchen_id == school.kitchen_id)
        .all()
    )
    return [
        {"id": i.id, "kitchen_id": i.kitchen_id, "name": i.name, "price": i.price}
        for i in items
    ]
