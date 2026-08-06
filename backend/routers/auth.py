"""
routers/auth.py
Module 1 — Authentication & Roles.
POST /auth/register — creates a new user (in the real product, restrict
                       this to Admins inviting people; left open here so
                       you can create your first user during development).
POST /auth/login    — verifies credentials, returns a JWT.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
from security import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=schemas.UserOut)
def register(payload: schemas.UserRegister, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="A user with this email already exists.")

    if payload.role not in ("admin", "manager", "employee", "client"):
        raise HTTPException(status_code=400, detail="Role must be admin, manager, employee, or client.")

    user = models.User(
        organization_id=payload.organization_id,
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2PasswordRequestForm sends "username" — we treat that field as email.
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account has been deactivated.")

    access_token = create_access_token({
        "sub": str(user.id),
        "role": user.role,
        "organization_id": str(user.organization_id),
    })
    return {"access_token": access_token, "token_type": "bearer", "user": user}