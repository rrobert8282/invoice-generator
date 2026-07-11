from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine
from app import models  # noqa: F401 -- registers models on Base.metadata before create_all
from app.routers import clients, invoices


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Phase 0: create tables directly so the app boots without a manual migration step.
    # Once Alembic migrations are established, replace this with `alembic upgrade head`
    # run before the app starts (e.g. in the Docker CMD or a Render deploy hook).
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Invoice Generator API", lifespan=lifespan)

app.include_router(clients.router)
app.include_router(invoices.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}