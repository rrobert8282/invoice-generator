from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routers import auth, clients, invoices


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is now managed by Alembic migrations (see docker-compose.yml's
    # api command, which runs `alembic upgrade head` before starting uvicorn),
    # not by create_all(). This is what makes schema changes safe against a
    # real database with real data, instead of requiring a full wipe each time.
    yield


app = FastAPI(title="Invoice Generator API", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(clients.router)
app.include_router(invoices.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}