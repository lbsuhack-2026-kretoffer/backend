from datetime import date, datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class BaseSchema(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


# --- Auth ---
class LoginInput(BaseSchema):
    login: str
    password: str


class ClassRef(BaseSchema):
    id: str
    name: str


class UserOut(BaseSchema):
    id: str
    full_name: str
    email: str
    role: str
    school_id: str | None = None
    school_name: str | None = None
    position: str | None = None
    avatar_url: str | None = None


class TeacherWithClassesOut(UserOut):
    classes: list[ClassRef] = []


# --- School ---
class AdminRef(BaseSchema):
    id: str
    full_name: str
    role: str
    position: str | None = None


class Integrations(BaseSchema):
    pos: bool = False
    skud: bool = False


class SchoolOut(BaseSchema):
    id: str
    name: str
    city: str
    address: str
    phone: str
    email: str
    meal_plan: str
    timezone: str
    buffer_percent: int
    attendance_deadline: str
    access_enabled: bool
    created_at: date
    integrations: Integrations
    admin_ids: list[str] = []
    classes_count: int = 0
    students_count: int = 0
    teachers_count: int = 0
    admins: list[AdminRef] = []


class SchoolCreateInput(BaseSchema):
    name: str
    city: str
    address: str
    phone: str
    email: str
    meal_plan: str = "fixed"
    timezone: str = "Europe/Minsk"
    buffer_percent: int = 8
    attendance_deadline: str = "09:15"
    admin_email: str | None = None
    admin_full_name: str | None = None
    admin_password: str | None = None


class SchoolPatchInput(BaseSchema):
    name: str | None = None
    city: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    meal_plan: str | None = None
    timezone: str | None = None
    buffer_percent: int | None = None
    attendance_deadline: str | None = None
    access_enabled: bool | None = None
    integrations: Integrations | None = None


class AddAdminInput(BaseSchema):
    email: str
    full_name: str
    password: str


class AccessToggleInput(BaseSchema):
    enabled: bool


# --- Class & Student ---
class AttendanceBlock(BaseSchema):
    status: str
    absent_count: int = 0
    submitted_at: str | None = None
    submitted_by_name: str | None = None


class ClassOut(BaseSchema):
    id: str
    school_id: str
    name: str
    grade: int
    age_group: str
    teacher_ids: list[str] = []
    teacher_names: list[str] = []
    students_count: int
    opt_outs_count: int
    attendance: AttendanceBlock | None = None


class ClassCreateInput(BaseSchema):
    name: str
    grade: int
    age_group: str | None = None
    teacher_id: str | None = None


class ClassPatchInput(BaseSchema):
    name: str | None = None
    grade: int | None = None
    age_group: str | None = None
    teacher_id: str | None = None


class AssignTeacherInput(BaseSchema):
    teacher_id: str


class StudentOut(BaseSchema):
    id: str
    school_id: str
    class_id: str
    full_name: str
    meal_status: str
    age_group: str
    card_number: str


class StudentWithClassOut(StudentOut):
    class_name: str


class StudentCreateInput(BaseSchema):
    full_name: str
    meal_status: str = "regular"


class StudentPatchInput(BaseSchema):
    full_name: str | None = None
    meal_status: str | None = None


class TeacherCreateInput(BaseSchema):
    full_name: str
    email: str
    position: str | None = "Учитель"
    password: str


# --- Attendance ---
class StudentMark(BaseSchema):
    id: str
    full_name: str
    meal_status: str
    card_number: str
    absent: bool


class AttendanceOut(BaseSchema):
    class_id: str
    class_name: str
    school_id: str
    school_name: str
    date: date
    deadline: str
    status: str
    absent_student_ids: list[str] = []
    submitted_at: str | None = None
    submitted_by_name: str | None = None
    total_students: int
    opt_outs: int
    students: list[StudentMark] = []


class AttendancePutInput(BaseSchema):
    date: date
    absent_student_ids: list[str] = []


class TeacherClassRow(BaseSchema):
    id: str
    name: str
    grade: int
    age_group: str
    students: int
    opt_outs: int
    absent: int
    present: int
    status: str
    submitted_at: str | None = None
    submitted_by_name: str | None = None


class TeacherClassesOut(BaseSchema):
    teacher: AdminRef
    school_name: str
    deadline: str
    date: date
    classes: list[TeacherClassRow] = []


class TeacherAttendanceItem(BaseSchema):
    date: date
    class_id: str
    class_name: str
    absent_count: int
    submitted_at: str
    status: str


class TeacherAttendanceOut(BaseSchema):
    date: date
    days: int
    items: list[TeacherAttendanceItem] = []


class AttendanceSummaryClass(BaseSchema):
    id: str
    name: str
    age_group: str
    students: int
    opt_outs: int
    absent: int
    present: int
    status: str
    submitted_at: str | None = None
    submitted_by_name: str | None = None
    teacher_names: list[str] = []


class AttendanceSummaryOut(BaseSchema):
    school_id: str
    date: date
    total_students: int
    opt_outs: int
    absent: int
    present: int
    marked_classes: int
    total_classes: int
    classes: list[AttendanceSummaryClass] = []


# --- Forecast ---
class AgeGroupRow(BaseSchema):
    age_group: str
    students: int
    opt_outs: int
    absent: int
    present: int
    portions: int


class CategoryRow(BaseSchema):
    id: str
    name: str
    qty: int
    revenue: float


class ForecastOut(BaseSchema):
    school_id: str
    school_name: str
    date: date
    meal_plan: str
    buffer_percent: int
    total_students: int
    opt_outs: int
    absent: int
    present: int
    total_portions: int
    adjustment_delta: int = 0
    adjustment_reason: str | None = None
    by_age_group: list[AgeGroupRow] = []
    by_category: list[CategoryRow] = []
    marked_classes: int
    total_classes: int
    based_on_date: date
    confidence: float
    status: str = "draft"
    approved_at: datetime | None = None
    approved_by: str | None = None
    comment: str = ""


class ApproveInput(BaseSchema):
    comment: str | None = ""


class ForecastHistoryRow(BaseSchema):
    date: date
    forecast: int
    actual: int
    waste_portions: int
    waste_cost: float
    accuracy: float
    confidence: float
    buffer_percent: int


class ForecastAdjustmentOut(BaseSchema):
    id: str
    school_id: str
    date: date
    delta: int
    reason: str | None = None
    created_by: str | None = None
    created_at: datetime | None = None


class AdjustmentInput(BaseSchema):
    delta: int
    reason: str | None = None


class CanteenHistoryRow(BaseSchema):
    date: date
    qty: int
    waste_qty: int


class CanteenForecastCategory(BaseSchema):
    id: str
    school_id: str
    name: str
    share: float
    avg_price: float
    unit: str
    qty: int
    revenue: float
    yesterday_qty: int
    waste_qty: int
    history: list[CanteenHistoryRow] = []


class CanteenForecastOut(ForecastOut):
    categories: list[CanteenForecastCategory] = []
    yesterday_date: date
    yesterday_total_qty: int
    total_forecast_qty: int
    expected_revenue: float


class CanteenSalesCategory(BaseSchema):
    id: str
    name: str
    qty: int
    revenue: float
    waste_qty: int


class CanteenSalesDay(BaseSchema):
    date: date
    total_qty: int
    revenue: float
    waste_qty: int
    by_category: list[CanteenSalesCategory] = []


class CanteenCategoryOut(BaseSchema):
    id: str
    school_id: str
    name: str
    share: float
    avg_price: float
    unit: str


class CanteenCategoryInput(BaseSchema):
    name: str
    share: float
    avg_price: float
    unit: str = "порция"


class CanteenCategoryPatch(BaseSchema):
    name: str | None = None
    share: float | None = None
    avg_price: float | None = None
    unit: str | None = None


# --- SKUD ---
class AccessEventOut(BaseSchema):
    id: str
    school_id: str
    student_id: str
    student_name: str
    class_name: str
    type: str
    source: str
    date: date
    time: str


class ManualAccessInput(BaseSchema):
    student_id: str
    type: str


# --- Platform ---
class PlatformAttendanceStats(BaseSchema):
    present: int
    absent: int
    opt_outs: int
    marked_classes: int
    total_classes: int
    date: date


class PlatformStatsOut(BaseSchema):
    schools: int
    active_schools: int
    students: int
    classes: int
    teachers: int
    attendance: PlatformAttendanceStats


class SchoolPage(BaseSchema):
    items: list[SchoolOut]
    total: int
    page: int
    page_size: int
