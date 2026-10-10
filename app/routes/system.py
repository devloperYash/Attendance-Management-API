from fastapi import APIRouter, HTTPException
from app.database import ping_db

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    if not ping_db():
        raise HTTPException(status_code=503, detail="Database connection unavailable")
    return {"status": "ok"}
