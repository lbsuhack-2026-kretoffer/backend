import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    full_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), default="")  # ← добавлен default
    role: Mapped[str] = mapped_column(String(32), index=True)
    position: Mapped[str | None] = mapped_column(String(128), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    school_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("schools.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    school: Mapped["School | None"] = relationship(back_populates="users", foreign_keys=[school_id])


class School(Base):
    __tablename__ = "schools"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(128))
    address: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(64), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    meal_plan: Mapped[str] = mapped_column(String(16), default="fixed")  # fixed | canteen
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Minsk")
    buffer_percent: Mapped[int] = mapped_column(Integer, default=10)
    attendance_deadline: Mapped[str] = mapped_column(String(5), default="09:00")
    access_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    integration_pos: Mapped[bool] = mapped_column(Boolean, default=False)
    integration_skud: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[list[User]] = relationship(back_populates="school", foreign_keys=[User.school_id])
    classes: Mapped[list["SchoolClass"]] = relationship(
        back_populates="school", cascade="all, delete-orphan"
    )
    students: Mapped[list["Student"]] = relationship(
        back_populates="school", cascade="all, delete-orphan"
    )


class SchoolClass(Base):
    __tablename__ = "classes"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    school_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("schools.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(64))
    grade: Mapped[int] = mapped_column(Integer)
    age_group: Mapped[str] = mapped_column(String(16), default="middle")  # junior|middle|senior
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    school: Mapped[School] = relationship(back_populates="classes")
    students: Mapped[list["Student"]] = relationship(
        back_populates="klass", cascade="all, delete-orphan"
    )
    teacher_links: Mapped[list["ClassTeacher"]] = relationship(
        back_populates="klass", cascade="all, delete-orphan"
    )


class ClassTeacher(Base):
    __tablename__ = "class_teachers"
    __table_args__ = (UniqueConstraint("class_id", "teacher_id", name="uq_class_teacher"),)
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    class_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("classes.id", ondelete="CASCADE"), index=True
    )
    teacher_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    klass: Mapped[SchoolClass] = relationship(back_populates="teacher_links")


class Student(Base):
    __tablename__ = "students"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    school_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("schools.id", ondelete="CASCADE"), index=True
    )
    class_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("classes.id", ondelete="CASCADE"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(255))
    meal_status: Mapped[str] = mapped_column(String(16), default="regular")  # regular|opt_out
    age_group: Mapped[str] = mapped_column(String(16), default="middle")
    card_number: Mapped[str | None] = mapped_column(String(64), nullable=True)

    school: Mapped[School] = relationship(back_populates="students")
    klass: Mapped[SchoolClass] = relationship(back_populates="students")


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("class_id", "date", name="uq_attendance_class_date"),)
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    school_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("schools.id", ondelete="CASCADE"), index=True
    )
    class_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("classes.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    absent_ids: Mapped[str] = mapped_column(String, default="")  # comma-separated ids
    submitted_by: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=True
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ForecastApproval(Base):
    __tablename__ = "forecast_approvals"
    __table_args__ = (UniqueConstraint("school_id", "date", name="uq_approval_school_date"),)
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    school_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("schools.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    comment: Mapped[str | None] = mapped_column(String(512), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ForecastAdjustment(Base):
    __tablename__ = "forecast_adjustments"
    __table_args__ = (UniqueConstraint("school_id", "date", name="uq_adjust_school_date"),)
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    school_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("schools.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    delta: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CanteenCategory(Base):
    __tablename__ = "canteen_categories"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    school_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("schools.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    share: Mapped[float] = mapped_column(Float, default=0.5)
    avg_price: Mapped[float] = mapped_column(Float, default=0)
    unit: Mapped[str] = mapped_column(String(16), default="порция")


class AccessEvent(Base):
    __tablename__ = "access_events"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    school_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("schools.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(8))  # entry|exit
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual|skud
    date: Mapped[date] = mapped_column(Date, index=True)
    time: Mapped[str] = mapped_column(String(8))  # HH:MM
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CanteenSale(Base):
    __tablename__ = "canteen_sales"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    school_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("schools.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("canteen_categories.id", ondelete="SET NULL"), nullable=True
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    qty: Mapped[int] = mapped_column(Integer, default=0)
    amount: Mapped[float] = mapped_column(Float, default=0)


class SchoolAdmin(Base):
    """Явная связь школа ↔ завуч, как просит api (3).md, п.4."""

    __tablename__ = "school_admins"
    __table_args__ = (UniqueConstraint("school_id", "user_id", name="uq_school_admin"),)
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    school_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("schools.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
