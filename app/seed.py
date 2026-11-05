import random
from datetime import date, datetime, timedelta

from app import models
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
MIDDLE = [
    "Александрович",
    "Дмитриевич",
    "Сергеевич",
    "Андреевич",
    "Алексеевна",
    "Дмитриевна",
    "Сергеевна",
    "Андреевна",
]


def _student_name() -> str:
    return f"{random.choice(LAST)} {random.choice(FIRST)}"


def _card(n: int) -> str:
    return f"C-{n:04d}"


def _make_students(
    db: Session, school_id: str, class_id: str, age_group: str, start_idx: int, count: int
) -> int:
    idx = start_idx
    for _ in range(count):
        idx += 1
        meal_status = "optOut" if random.random() < 0.08 else "regular"
        db.add(
            models.Student(
                id=f"s-{idx}",
                school_id=school_id,
                class_id=class_id,
                full_name=_student_name(),
                meal_status=meal_status,
                age_group=age_group,
                card_number=_card(idx),
            )
        )
    return idx


def _make_attendance_history(
    db: Session, class_id: str, students_ids: list[str], teacher_id: str, days: int = 14
) -> None:
    today = date.today()
    for delta in range(days, 0, -1):
        d = today - timedelta(days=delta)
        if d.weekday() >= 5:  # пропускаем выходные
            continue
        absent = random.sample(students_ids, k=min(len(students_ids), random.randint(0, 2)))
        submitted = datetime.combine(d, datetime.min.time()).replace(
            hour=9, minute=random.randint(0, 20)
        )
        db.add(
            models.AttendanceRecord(
                id=f"att-{class_id}-{d.isoformat()}",
                class_id=class_id,
                date=d,
                submitted_at=submitted,
                submitted_by_id=teacher_id,
                absent_student_ids=absent,
            )
        )


def seed_demo(db: Session) -> None:
    if db.query(models.School).count() > 0:
        return

    # --- Пользователи платформы ---
    platform_admin = models.User(
        id="u-platform",
        full_name="Ирина Ковалёва",
        email="admin@school-balance.by",
        role="platform_admin",
        position="Администратор платформы",
    )
    db.add(platform_admin)

    # --- Школа A: Гимназия №12 ---
    school_a = models.School(
        id="school-a",
        name="Гимназия №12",
        city="Минск",
        address="ул. Кальварийская, 12",
        phone="+375 17 200-12-12",
        email="gym12@edu.by",
        meal_plan="fixed",
        timezone="Europe/Minsk",
        buffer_percent=10,
        attendance_deadline="09:30",
        access_enabled=True,
        integration_pos=False,
        integration_skud=True,
        created_at=date(2025, 9, 1),
    )
    db.add(school_a)

    admin_a = models.User(
        id="u-school-a",
        full_name="Ольга Петрова",
        email="petrova@gym12.by",
        role="school_admin",
        school_id="school-a",
        position="Завуч",
    )
    db.add(admin_a)
    db.add(models.SchoolAdmin(school_id="school-a", user_id="u-school-a"))

    t_a1 = models.User(
        id="u-teach-a-1",
        full_name="Марина Соловьёва",
        email="soloveva@gym12.by",
        role="teacher",
        school_id="school-a",
        position="Учитель начальных классов",
    )
    t_a2 = models.User(
        id="u-teach-a-2",
        full_name="Алексей Морозов",
        email="morozov@gym12.by",
        role="teacher",
        school_id="school-a",
        position="Учитель математики",
    )
    t_a3 = models.User(
        id="u-teach-a-3",
        full_name="Елена Кузнецова",
        email="kuznecova@gym12.by",
        role="teacher",
        school_id="school-a",
        position="Учитель русского языка",
    )
    db.add_all([t_a1, t_a2, t_a3])

    canteen_a = models.User(
        id="u-canteen-a",
        full_name="Наталья Смирнова",
        email="canteen@gym12.by",
        role="canteen",
        school_id="school-a",
        position="Заведующая столовой",
    )
    guard_a = models.User(
        id="u-guard-a",
        full_name="Виктор Зайцев",
        email="guard@gym12.by",
        role="guard",
        school_id="school-a",
        position="Охранник",
    )
    db.add_all([canteen_a, guard_a])

    # --- Школа B: Средняя школа №34 (шведский стол) ---
    school_b = models.School(
        id="school-b",
        name="Средняя школа №34",
        city="Минск",
        address="пр-т Независимости, 34",
        phone="+375 17 765-43-21",
        email="sch34@edu.by",
        meal_plan="canteen",
        timezone="Europe/Minsk",
        buffer_percent=8,
        attendance_deadline="09:15",
        access_enabled=False,
        integration_pos=True,
        integration_skud=False,
        created_at=date(2025, 9, 1),
    )
    db.add(school_b)

    admin_b = models.User(
        id="u-school-b",
        full_name="Дмитрий Лебедев",
        email="lebedev@sch34.by",
        role="school_admin",
        school_id="school-b",
        position="Завуч",
    )
    db.add(admin_b)
    db.add(models.SchoolAdmin(school_id="school-b", user_id="u-school-b"))

    t_b1 = models.User(
        id="u-teach-b-1",
        full_name="Ирина Новикова",
        email="novikova@sch34.by",
        role="teacher",
        school_id="school-b",
        position="Учитель начальных классов",
    )
    t_b2 = models.User(
        id="u-teach-b-2",
        full_name="Павел Орлов",
        email="orlov@sch34.by",
        role="teacher",
        school_id="school-b",
        position="Учитель истории",
    )
    db.add_all([t_b1, t_b2])

    canteen_b = models.User(
        id="u-canteen-b",
        full_name="Светлана Романова",
        email="canteen@sch34.by",
        role="canteen",
        school_id="school-b",
        position="Заведующая столовой",
    )
    db.add(canteen_b)

    db.flush()

    # --- Классы школы A ---
    classes_a = [
        ("class-a-2a", "2А", 2, "junior", [t_a1]),
        ("class-a-6a", "6А", 6, "middle", [t_a2]),
        ("class-a-10a", "10А", 10, "senior", [t_a3]),
    ]
    idx = 0
    for cid, name, grade, age_group, teachers in classes_a:
        db.add(
            models.SchoolClass(
                id=cid,
                school_id="school-a",
                name=name,
                grade=grade,
                age_group=age_group,
            )
        )
        for t in teachers:
            db.add(models.ClassTeacher(class_id=cid, teacher_id=t.id))
        count = 25
        start = idx
        idx = _make_students(db, "school-a", cid, age_group, idx, count)
        ids = [f"s-{i}" for i in range(start + 1, idx + 1)]
        _make_attendance_history(db, cid, ids, teachers[0].id)

    # --- Классы школы B ---
    classes_b = [
        ("class-b-1a", "1А", 1, "junior", [t_b1]),
        ("class-b-5a", "5А", 5, "middle", [t_b2]),
    ]
    for cid, name, grade, age_group, teachers in classes_b:
        db.add(
            models.SchoolClass(
                id=cid,
                school_id="school-b",
                name=name,
                grade=grade,
                age_group=age_group,
            )
        )
        for t in teachers:
            db.add(models.ClassTeacher(class_id=cid, teacher_id=t.id))
        start = idx
        idx = _make_students(db, "school-b", cid, age_group, idx, 25)
        ids = [f"s-{i}" for i in range(start + 1, idx + 1)]
        _make_attendance_history(db, cid, ids, teachers[0].id)

    # --- Категории столовой школы B ---
    categories_b = [
        ("cat-hot", "Горячее", 0.42, 4.2, "порция"),
        ("cat-salad", "Салаты", 0.18, 2.5, "порция"),
        ("cat-bakery", "Выпечка", 0.22, 1.8, "шт"),
        ("cat-drink", "Напитки", 0.18, 1.5, "стакан"),
    ]
    for cid, name, share, price, unit in categories_b:
        db.add(
            models.CanteenCategory(
                id=cid,
                school_id="school-b",
                name=name,
                share=share,
                avg_price=price,
                unit=unit,
            )
        )

    db.flush()

    # --- История продаж столовой школы B (14 дней) ---
    today = date.today()
    for delta in range(14, 0, -1):
        d = today - timedelta(days=delta)
        if d.weekday() >= 5:
            continue
        for cid, name, share, price, unit in categories_b:  # noqa B007
            base_qty = int(50 * 0.88 * share)
            qty = max(0, base_qty + random.randint(-3, 3))
            waste = random.randint(0, 2)
            db.add(
                models.CanteenSale(
                    id=f"sale-{cid}-{d.isoformat()}",
                    school_id="school-b",
                    date=d,
                    category_id=cid,
                    qty=qty,
                    revenue=round(qty * price, 2),
                    waste_qty=waste,
                )
            )

    # --- События СКУД школы A (за сегодня) ---
    students_a = db.query(models.Student).filter_by(school_id="school-a").limit(20).all()
    for i, s in enumerate(students_a):
        db.add(
            models.AccessEvent(
                id=f"evt-{1000 + i}",
                school_id="school-a",
                student_id=s.id,
                type="entry",
                source="turnstile",
                date=today,
                time=f"08:{30 + i % 30:02d}",
            )
        )

    db.commit()
