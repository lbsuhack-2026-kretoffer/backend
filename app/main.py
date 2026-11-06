from contextlib import asynccontextmanager

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.routers import attendance, auth, canteen, forecast, platform, schools, skud
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if settings.seed_demo:
        from app.seed import seed_demo

        with SessionLocal() as db:
            seed_demo(db)
    yield


app = FastAPI(title="Школьный Баланс-Пит API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API = settings.api_prefix
app.include_router(auth.router, prefix=API)
app.include_router(platform.router, prefix=API)
app.include_router(schools.router, prefix=API)
app.include_router(attendance.router, prefix=API)
app.include_router(forecast.router, prefix=API)
app.include_router(canteen.router, prefix=API)
app.include_router(skud.router, prefix=API)


@app.get("/health")
def health():
    return {"status": "ok"}
