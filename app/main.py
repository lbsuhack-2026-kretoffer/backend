from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import settings
from .database import Base, SessionLocal, engine
from .routers import (
    attendance,
    auth,
    canteen,
    classes,
    forecast,
    guard,
    platform,
    schools,
    students,
    teachers,
)
from .seed import seed_superadmin


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[startup] создаём таблицы...", flush=True)
    Base.metadata.create_all(bind=engine)
    print("[startup] таблицы готовы, сидируем супер-админа...", flush=True)
    db = SessionLocal()
    try:
        seed_superadmin(db)
    finally:
        db.close()
    print("[startup] бэкенд готов", flush=True)
    yield


app = FastAPI(title="Школьный Баланс-Пит API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def http_exc_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exc_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Некорректные данные: "
            + "; ".join(f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors())
        },
    )


API = "/api/v1"
app.include_router(auth.router, prefix=API)
app.include_router(platform.router, prefix=API)
app.include_router(schools.router, prefix=API)
app.include_router(classes.router, prefix=API)
app.include_router(students.router, prefix=API)
app.include_router(teachers.router, prefix=API)
app.include_router(attendance.router, prefix=API)
app.include_router(forecast.router, prefix=API)
app.include_router(canteen.router, prefix=API)
app.include_router(guard.router, prefix=API)


@app.get("/health")
def health():
    return {"status": "ok"}
