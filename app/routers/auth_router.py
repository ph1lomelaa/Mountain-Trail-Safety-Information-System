from fastapi import APIRouter, Depends
from app.auth import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/me")
def get_me(user=Depends(get_current_user)):
    return {k: v for k, v in user.items() if k != "password_hash"}
