from datetime import date, datetime

from app.database import Base
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    role = Column(String, nullable=False)
    school_id = Column(String, ForeignKey("schools.id"), nullable=True)
    position = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    created_at = Column(Date, nullable=False, default=date.today)


class School(Base):
    __tablename__ = "schools"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    city = Column(String, nullable=False)
    address = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    email = Column(String, nullable=False)
    meal_plan = Column(String, nullable=False, default="fixed")
    timezone = Column(String, default="Europe/Minsk")
    buffer_percent = Column(Integer, default=8)
    attendance_deadline = Column(String, default="09:15")
    access_enabled = Column(Boolean, default=False)
    integration_pos = Column(Boolean, default=False)
    integration_skud = Column(Boolean, default=False)
    created_at = Column(Date, nullable=False, default=date.today)


class SchoolAdmin(Base):
    __tablename__ = "school_admins"
    school_id = Column(String, ForeignKey("schools.id"), primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), primary_key=True)


class SchoolClass(Base):
    __tablename__ = "classes"
    id = Column(String, primary_key=True)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    name = Column(String, nullable=False)
    grade = Column(Integer, nullable=False)
    age_group = Column(String, nullable=False)


class ClassTeacher(Base):
    __tablename__ = "class_teachers"
    class_id = Column(String, ForeignKey("classes.id"), primary_key=True)
    teacher_id = Column(String, ForeignKey("users.id"), primary_key=True)


class Student(Base):
    __tablename__ = "students"
    id = Column(String, primary_key=True)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    class_id = Column(String, ForeignKey("classes.id"), nullable=False)
    full_name = Column(String, nullable=False)
    meal_status = Column(String, default="regular")
    age_group = Column(String, nullable=False)
    card_number = Column(String, nullable=False)


class AttendanceRecord(Base):
    __tablename__ = "attendance"
    id = Column(String, primary_key=True)
    class_id = Column(String, ForeignKey("classes.id"), nullable=False)
    date = Column(Date, nullable=False)
    submitted_at = Column(DateTime, nullable=False)
    submitted_by_id = Column(String, ForeignKey("users.id"), nullable=False)
    absent_student_ids = Column(JSON, default=list)
    __table_args__ = (UniqueConstraint("class_id", "date", name="uq_attendance_class_date"),)


class ForecastApproval(Base):
    __tablename__ = "forecast_approvals"
    id = Column(String, primary_key=True)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    date = Column(Date, nullable=False)
    approved_at = Column(DateTime, nullable=False)
    approved_by_id = Column(String, ForeignKey("users.id"), nullable=False)
    comment = Column(String, default="")
    __table_args__ = (UniqueConstraint("school_id", "date", name="uq_approval_school_date"),)


class CanteenCategory(Base):
    __tablename__ = "canteen_categories"
    id = Column(String, primary_key=True)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    name = Column(String, nullable=False)
    share = Column(Float, nullable=False)
    avg_price = Column(Float, nullable=False)
    unit = Column(String, default="порция")


class CanteenSale(Base):
    __tablename__ = "canteen_sales"
    id = Column(String, primary_key=True)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    date = Column(Date, nullable=False)
    category_id = Column(String, ForeignKey("canteen_categories.id"), nullable=False)
    qty = Column(Integer, nullable=False)
    revenue = Column(Float, nullable=False)
    waste_qty = Column(Integer, default=0)
    __table_args__ = (
        UniqueConstraint("school_id", "date", "category_id", name="uq_sale_school_date_cat"),
    )


class AccessEvent(Base):
    __tablename__ = "access_events"
    id = Column(String, primary_key=True)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    student_id = Column(String, ForeignKey("students.id"), nullable=False)
    type = Column(String, nullable=False)  # entry | exit
    source = Column(String, nullable=False)  # turnstile | manual
    date = Column(Date, nullable=False)
    time = Column(String, nullable=False)  # "08:47"
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
