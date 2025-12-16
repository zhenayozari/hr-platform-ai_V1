from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from ..database import get_db
from ..models import Company, User, PipelineStage, EmailTemplate
from ..auth.dependencies import get_current_user, get_current_active_admin
from ..auth.utils import get_password_hash

router = APIRouter(prefix="/settings", tags=["Настройки"])

# --- СХЕМЫ ---
class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    website: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None

class UserCreate(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str = ""
    role: str = "recruiter"

class UserInCompany(BaseModel):
    id: int
    email: str
    first_name: str
    last_name: str
    role: str
    is_active: bool
    last_login: Optional[datetime]
    class Config:
        from_attributes = True

class UserRoleUpdate(BaseModel):
    role: str        

# --- ЭНДПОИНТЫ ---

@router.get("/company")
def get_company_profile(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Company).filter(Company.id == current_user.company_id).first()

@router.patch("/company")
def update_company_profile(data: CompanyUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    for field, value in data.dict(exclude_unset=True).items():
        setattr(company, field, value)
    db.commit()
    return company

@router.get("/users", response_model=List[UserInCompany])
def get_company_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(User).filter(User.company_id == current_user.company_id).all()

@router.post("/users", response_model=UserInCompany)
def create_user(data: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email занят")
    
    user = User(
        email=data.email,
        hashed_password=get_password_hash(data.password),
        first_name=data.first_name,
        last_name=data.last_name,
        role=data.role,
        company_id=current_user.company_id
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.patch("/users/{user_id}/role", response_model=UserInCompany)
def update_user_role(
    user_id: int,
    data: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    """Изменить роль пользователя"""
    user = db.query(User).filter(
        User.id == user_id,
        User.company_id == current_user.company_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Защита от дурака: нельзя изменить роль самому себе
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Нельзя изменить свою роль")
    
    user.role = data.role
    db.commit()
    db.refresh(user)
    return user

@router.delete("/users/{user_id}")
def deactivate_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    user = db.query(User).filter(User.id == user_id, User.company_id == current_user.company_id).first()
    if not user: raise HTTPException(status_code=404, detail="Не найден")
    if user.id == current_user.id: raise HTTPException(status_code=400, detail="Нельзя удалить себя")
    
    user.is_active = False
    db.commit()
    return {"status": "ok"}