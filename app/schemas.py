from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


# ---- Auth
class LoginInput(BaseModel):
    login: str
    password: str


class PlatformAdminInput(BaseModel):
    fullName: str
    email: EmailStr
    password: str


class ChangeLoginInput(BaseModel):
    currentPassword: str = Field(min_length=1)
    newEmail: EmailStr


class ChangePasswordInput(BaseModel):
    currentPassword: str = Field(min_length=1)
    newPassword: str = Field(min_length=4)


class UserOut(BaseModel):
    id: str
    fullName: str
    email: str
    role: str
    schoolId: str | None = None
    schoolName: str | None = None
    district: str | None = None
    position: str | None = None
    avatarUrl: str | None = None


# ---- School
class SchoolIntegration(BaseModel):
    pos: bool = False
    skud: bool = False


class SchoolOut(BaseModel):
    id: str
    name: str
    city: str
    district: str
    address: str
    phone: str
    email: str
    mealPlan: str
    bufferPercent: int
    attendanceDeadline: str
    accessEnabled: bool
    createdAt: datetime
    integrations: SchoolIntegration
    adminIds: list[str]
    classesCount: int
    studentsCount: int
    teachersCount: int
    admins: list[dict]
    kitchenId: str | None = None
    kitchenName: str | None = None


class SchoolInput(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    city: str = Field(min_length=1, max_length=64)
    address: str = Field(min_length=1, max_length=256)
    phone: str = Field(min_length=1, max_length=32)
    email: str = Field(min_length=1, max_length=128)
    mealPlan: Literal["fixed", "canteen"] = "fixed"
    bufferPercent: int = Field(ge=0, le=100, default=10)
    attendanceDeadline: str = Field(min_length=1, max_length=8)
    district: str = Field(default="", max_length=128)
    adminEmail: EmailStr | None = None
    adminFullName: str | None = Field(default=None, max_length=128)
    adminPassword: str | None = Field(default=None, min_length=4)


class SchoolPatch(BaseModel):
    name: str | None = None
    city: str | None = None
    district: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    mealPlan: Literal["fixed", "canteen"] | None = None
    bufferPercent: int | None = None
    attendanceDeadline: str | None = None
    integrations: SchoolIntegration | None = None


class SchoolAdminInput(BaseModel):
    email: EmailStr
    fullName: str
    password: str = Field(min_length=4)


class AccessToggle(BaseModel):
    enabled: bool


# ---- Class
class ClassOut(BaseModel):
    id: str
    schoolId: str
    name: str
    grade: int
    ageGroup: str
    teacherIds: list[str]
    teacherNames: list[str]
    studentsCount: int
    optOutsCount: int
    attendance: dict | None = None


class ClassInput(BaseModel):
    name: str
    grade: int
    ageGroup: str | None = None
    teacherId: str | None = None


class ClassCreateWithStudentsInput(BaseModel):
    grade: int = Field(ge=1, le=11, description="Класс 1–11")
    letter: str = Field(min_length=1, max_length=2, description="Буква класса, например А")
    studentsCount: int = Field(ge=1, le=60, description="Количество учеников")
    studentNames: list[str] = Field(min_length=1, max_length=60, description="ФИО учеников")


class ClassPatch(BaseModel):
    name: str | None = None
    grade: int | None = Field(default=None, ge=1, le=11)
    ageGroup: str | None = None
    teacherId: str | None = None


class TeacherAssign(BaseModel):
    teacherId: str


# ---- Student
class StudentOut(BaseModel):
    id: str
    schoolId: str
    classId: str
    fullName: str
    mealStatus: str
    ageGroup: str
    cardNumber: str | None
    className: str | None = None


class StudentInput(BaseModel):
    fullName: str
    mealStatus: Literal["regular", "opt_out"] = "regular"


class StudentPatch(BaseModel):
    fullName: str | None = None
    mealStatus: Literal["regular", "opt_out"] | None = None


# ---- Teacher
class TeacherOut(BaseModel):
    id: str
    fullName: str
    email: str
    role: str
    schoolId: str | None = None
    position: str | None = None
    classes: list[dict] = []


class TeacherInput(BaseModel):
    fullName: str
    email: EmailStr
    position: str | None = None
    password: str = Field(min_length=4)
    role: Literal["teacher", "guard"] = "teacher"


# ---- Attendance
class AttendancePut(BaseModel):
    date: date
    absentStudentIds: list[str]


# ---- Adjust
class AdjustInput(BaseModel):
    delta: int
    reason: str | None = None


class ApproveInput(BaseModel):
    comment: str | None = None


# ---- Canteen
class CanteenCategoryInput(BaseModel):
    name: str
    share: float = Field(ge=0, le=1)
    avgPrice: float = 0
    unit: Literal["порция", "шт", "стакан", "комплект"] = "порция"


class CanteenCategoryPatch(BaseModel):
    name: str | None = None
    share: float | None = Field(default=None, ge=0, le=1)
    avgPrice: float | None = None
    unit: Literal["порция", "шт", "стакан", "комплект"] | None = None


# ---- Guard
class AccessEventInput(BaseModel):
    studentId: str
    type: Literal["entry", "exit"]


# ---- Kitchen (Canteen kitchen / комбинат питания района)
class KitchenOut(BaseModel):
    id: str
    name: str
    district: str


class KitchenInput(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    district: str = Field(min_length=1, max_length=128)
    email: EmailStr | None = None
    fullName: str | None = None
    password: str | None = Field(default=None, min_length=4)


class MenuItemOut(BaseModel):
    id: str
    kitchen_id: str
    name: str
    price: float


class MenuItemInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    price: float = Field(ge=0, le=100000)


class KitchenUserInput(BaseModel):
    email: EmailStr
    fullName: str
    password: str = Field(min_length=4)


class KitchenPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    district: str | None = Field(default=None, min_length=1, max_length=128)
    email: EmailStr | None = None
    fullName: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, min_length=4)


class SchoolKitchenPatch(BaseModel):
    kitchenId: str | None = None
