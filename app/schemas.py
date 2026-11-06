from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


# ---- Auth
class LoginInput(BaseModel):
    login: str
    password: str


class UserOut(BaseModel):
    id: str
    fullName: str
    email: str
    role: str
    schoolId: str | None = None
    schoolName: str | None = None
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
    address: str
    phone: str
    email: str
    mealPlan: str
    timezone: str
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


class SchoolInput(BaseModel):
    name: str
    city: str
    address: str = ""
    phone: str = ""
    email: str = ""
    mealPlan: Literal["fixed", "canteen"] = "fixed"
    timezone: str = "Europe/Minsk"
    bufferPercent: int = 10
    attendanceDeadline: str = "09:00"
    adminEmail: EmailStr | None = None
    adminFullName: str | None = None
    adminPassword: str | None = None


class SchoolPatch(BaseModel):
    name: str | None = None
    city: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    mealPlan: Literal["fixed", "canteen"] | None = None
    timezone: str | None = None
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


class ClassPatch(BaseModel):
    name: str | None = None
    grade: int | None = None
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
