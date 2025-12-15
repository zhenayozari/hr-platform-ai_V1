from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from .utils import decode_token

# Схема авторизации через Bearer token
security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Извлекает текущего пользователя из JWT токена.
    Используется как зависимость в защищённых эндпоинтах.
    """
    token = credentials.credentials
    
    # Декодируем токен
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Извлекаем user_id из токена
    user_id: int = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Токен не содержит информации о пользователе",
        )
    
    # Находим пользователя в базе
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Аккаунт деактивирован",
        )
    
    return user

async def get_current_active_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """Проверяет, что пользователь — администратор"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав. Требуется роль admin.",
        )
    return current_user

async def get_current_recruiter_or_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """Проверяет, что пользователь — рекрутер или админ"""
    if current_user.role not in ["admin", "recruiter"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав. Требуется роль recruiter или admin.",
        )
    return current_user