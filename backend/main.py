from app.api.livekit import router as livekit_router
from app.api.routes import router as api_router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Me-Mex Backend", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(livekit_router)


@app.get("/")
def read_root():
    return {"status": "online", "system": "Me-Mex Engine"}
