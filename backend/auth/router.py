from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta

from .dependencies import get_current_user

from ..database import get_db
from ..models import User, Company
from .utils import verify_password, get_password_hash, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter(prefix="/auth", tags=["Аутентификация"])

# --- СХЕМЫ ---

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str = ""
    company_name: str  # Название компании (создаём новую или находим)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

class UserResponse(BaseModel):
    id: int
    email: str
    first_name: str
    last_name: str
    role: str
    company_id: int
    company_name: str
    
    class Config:
        from_attributes = True

# --- ЭНДПОИНТЫ ---

@router.post("/register", response_model=TokenResponse)
def register(data: UserRegister, db: Session = Depends(get_db)):
    """
    Регистрация нового пользователя.
    Если компания с таким названием не существует — создаёт её.
    Первый пользователь компании становится admin.
    """
    # Проверяем, что email не занят
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователь с таким email уже существует"
        )
    
    # Находим или создаём компанию
    company = db.query(Company).filter(Company.name == data.company_name).first()
    if not company:
        company = Company(name=data.company_name)
        db.add(company)
        db.commit()
        db.refresh(company)
    
    # Определяем роль: первый пользователь компании = admin
    existing_users_count = db.query(User).filter(User.company_id == company.id).count()
    role = "admin" if existing_users_count == 0 else "recruiter"
    
    # Создаём пользователя
    user = User(
        email=data.email,
        hashed_password=get_password_hash(data.password),
        first_name=data.first_name,
        last_name=data.last_name,
        role=role,
        company_id=company.id
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Создаём токен
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "company_id": user.company_id,
            "company_name": company.name
        }
    }

@router.post("/login", response_model=TokenResponse)
def login(data: UserLogin, db: Session = Depends(get_db)):
    """Авторизация пользователя"""
    # Ищем пользователя
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль"
        )
    
    # Проверяем пароль
    if not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль"
        )
    
    # Проверяем активность
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Аккаунт деактивирован"
        )
    
    # Обновляем last_login
    user.last_login = datetime.utcnow()
    db.commit()
    
    # Создаём токен
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "company_id": user.company_id,
            "company_name": user.company.name
        }
    }

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Получить информацию о текущем пользователе"""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "role": current_user.role,
        "company_id": current_user.company_id,
        "company_name": current_user.company.name
    }