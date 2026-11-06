import random
from datetime import date, datetime, timedelta

from app import models
from app.auth import get_password_hash
from sqlalchemy.orm import Session

random.seed(42)

FIRST = [
    "Артём",
    "Илья",
    "Максим",
    "Даниил",
    "Кирилл",
    "Егор",
    "Анна",
    "Мария",
    "София",
    "Полина",
    "Ева",
    "Варвара",
    "Дарья",
    "Алиса",
    "Милана",
    "Тимофей",
    "Роман",
    "Никита",
    "Глеб",
    "Лев",
]
LAST = [
    "Соколов",
    "Абрамов",
    "Иванов",
    "Петров",
    "Сидоров",
    "Морозов",
    "Козлов",
    "Смирнов",
    "Волков",
    "Зайцев",
    "Павлов",
    "Семёнов",
    "Голубев",
    "Виноградов",
    "Богданов",
    "Воробьёв",
    "Фёдоров",
    "Михайлов",
    "Беляев",
    "Тарасов",
]


def _student_name() -> str:
    return f"{random.choice(LAST)} {random.choice(FIRST)}"


def _card(n: int) -> str:
    return f"C-{n:04d}"


def _make_students(db, school_id, class_id, age_group, start_idx, count):
    idx = start_idx
    for _ in range(count):
        idx += 1
        db.add(
            models.Student(
                id=f"s-{idx}",
                school_id=school_id,
                class_id=class_id,
                full_name=_student_name(),
                meal_status="optOut" if random.random() < 0.08 else "regular",
                age_group=age_group,
                card_number=_card(idx),
            )
        )
    return idx


def _make_attendance_history(db, class_id, students_ids, teacher_id, days=14):
    today = date.today()
    for delta in range(days, 0, -1):
        d = today - timedelta(days=delta)
        if d.weekday() >= 5:
            continue
        absent = random.sample(students_ids, k=min(len(students_ids), random.randint(0, 2)))
        db.add(
            models.AttendanceRecord(
                id=f"att-{class_id}-{d.isoformat()}",
                class_id=class_id,
                date=d,
                submitted_at=datetime.combine(d, datetime.min.time()).replace(
                    hour=9, minute=random.randint(0, 20)
                ),
                submitted_by_id=teacher_id,
                absent_student_ids=absent,
            )
        )


def seed_demo(db: Session) -> None:
    if db.query(models.School).count() > 0:
        return
    pwd = get_password_hash("secret123")

    # Платформа
    db.add(
        models.User(
            id="u-platform",
            full_name="Ирина Ковалёва",
            email="admin@school-balance.by",
            password_hash=pwd,
            role="platform_admin",
            position="Администратор платформы",
        )
    )

    # Школа A
    db.add(
        models.School(
            id="school-a",
            name="Гимназия №12",
            city="Минск",
            address="ул. Кальварийская, 12",
            phone="+375 17 200-12-12",
            email="gym12@edu.by",
            meal_plan="fixed",
            buffer_percent=10,
            created_at=date(2025, 9, 1),
        )
    )
    admin_a = models.User(
        id="u-school-a",
        full_name="Ольга Петрова",
        email="petrova@gym12.by",
        role="school_admin",
        school_id="school-a",
        position="Завуч",
        password_hash=pwd,
    )
    t_a1 = models.User(
        id="u-teach-a-1",
        full_name="Марина Соловьёва",
        email="soloveva@gym12.by",
        role="teacher",
        school_id="school-a",
        position="Учитель начальных классов",
        password_hash=pwd,
    )
    t_a2 = models.User(
        id="u-teach-a-2",
        full_name="Алексей Морозов",
        email="morozov@gym12.by",
        role="teacher",
        school_id="school-a",
        position="Учитель математики",
        password_hash=pwd,
    )
    t_a3 = models.User(
        id="u-teach-a-3",
        full_name="Елена Кузнецова",
        email="kuznecova@gym12.by",
        role="teacher",
        school_id="school-a",
        position="Учитель русского языка",
        password_hash=pwd,
    )
    db.add_all([admin_a, t_a1, t_a2, t_a3])
    db.add(models.SchoolAdmin(school_id="school-a", user_id="u-school-a"))
    db.add_all(
        [
            models.User(
                id="u-canteen-a",
                full_name="Наталья Смирнова",
                email="canteen@gym12.by",
                role="canteen",
                school_id="school-a",
                position="Заведующая столовой",
                password_hash=pwd,
            ),
            models.User(
                id="u-guard-a",
                full_name="Виктор Зайцев",
                email="guard@gym12.by",
                role="guard",
                school_id="school-a",
                position="Охранник",
                password_hash=pwd,
            ),
        ]
    )

    # Школа B
    db.add(
        models.School(
            id="school-b",
            name="Средняя школа №34",
            city="Минск",
            address="пр-т Независимости, 34",
            phone="+375 17 765-43-21",
            email="sch34@edu.by",
            meal_plan="canteen",
            buffer_percent=8,
            created_at=date(2025, 9, 1),
        )
    )
    admin_b = models.User(
        id="u-school-b",
        full_name="Дмитрий Лебедев",
        email="lebedev@sch34.by",
        role="school_admin",
        school_id="school-b",
        position="Завуч",
        password_hash=pwd,
    )
    t_b1 = models.User(
        id="u-teach-b-1",
        full_name="Ирина Новикова",
        email="novikova@sch34.by",
        role="teacher",
        school_id="school-b",
        position="Учитель начальных классов",
        password_hash=pwd,
    )
    t_b2 = models.User(
        id="u-teach-b-2",
        full_name="Павел Орлов",
        email="orlov@sch34.by",
        role="teacher",
        school_id="school-b",
        position="Учитель истории",
        password_hash=pwd,
    )
    db.add_all([admin_b, t_b1, t_b2])
    db.add(models.SchoolAdmin(school_id="school-b", user_id="u-school-b"))
    db.add(
        models.User(
            id="u-canteen-b",
            full_name="Светлана Романова",
            email="canteen@sch34.by",
            role="canteen",
            school_id="school-b",
            position="Заведующая столовой",
            password_hash=pwd,
        )
    )
    db.flush()

    # Классы
    idx = 0
    for cid, name, grade, age, teachers in [
        ("class-a-2a", "2А", 2, "junior", [t_a1]),
        ("class-a-6a", "6А", 6, "middle", [t_a2]),
        ("class-a-10a", "10А", 10, "senior", [t_a3]),
    ]:
        db.add(
            models.SchoolClass(id=cid, school_id="school-a", name=name, grade=grade, age_group=age)
        )
        for t in teachers:
            db.add(models.ClassTeacher(class_id=cid, teacher_id=t.id))
        start = idx
        idx = _make_students(db, "school-a", cid, age, idx, 25)
        _make_attendance_history(
            db, cid, [f"s-{i}" for i in range(start + 1, idx + 1)], teachers[0].id
        )

    for cid, name, grade, age, teachers in [
        ("class-b-1a", "1А", 1, "junior", [t_b1]),
        ("class-b-5a", "5А", 5, "middle", [t_b2]),
    ]:
        db.add(
            models.SchoolClass(id=cid, school_id="school-b", name=name, grade=grade, age_group=age)
        )
        for t in teachers:
            db.add(models.ClassTeacher(class_id=cid, teacher_id=t.id))
        start = idx
        idx = _make_students(db, "school-b", cid, age, idx, 25)
        _make_attendance_history(
            db, cid, [f"s-{i}" for i in range(start + 1, idx + 1)], teachers[0].id
        )

    # Категории и продажи
    cats = [
        ("cat-hot", "Горячее", 0.42, 4.2, "порция"),
        ("cat-salad", "Салаты", 0.18, 2.5, "порция"),
        ("cat-bakery", "Выпечка", 0.22, 1.8, "шт"),
        ("cat-drink", "Напитки", 0.18, 1.5, "стакан"),
    ]
    for cid, name, share, price, unit in cats:
        db.add(
            models.CanteenCategory(
                id=cid, school_id="school-b", name=name, share=share, avg_price=price, unit=unit
            )
        )
    db.flush()

    today = date.today()
    for delta in range(14, 0, -1):
        d = today - timedelta(days=delta)
        if d.weekday() >= 5:
            continue
        for cid, name, share, price, unit in cats:  # noqa B007
            qty = max(0, int(50 * 0.88 * share) + random.randint(-3, 3))
            db.add(
                models.CanteenSale(
                    id=f"sale-{cid}-{d.isoformat()}",
                    school_id="school-b",
                    date=d,
                    category_id=cid,
                    qty=qty,
                    revenue=round(qty * price, 2),
                    waste_qty=random.randint(0, 2),
                )
            )

    db.commit()
