from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime, Boolean, Float
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    
    # Связи
    users = relationship("User", back_populates="company")
    vacancies = relationship("Vacancy", back_populates="company")
    candidates = relationship("Candidate", back_populates="company")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    role = Column(String, default="recruiter") # admin, recruiter
    is_active = Column(Boolean, default=True)
    
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    company = relationship("Company", back_populates="users")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

class Vacancy(Base):
    __tablename__ = "vacancies"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(Text)
    requirements = Column(Text)
    status = Column(String, default="active")
    
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    company = relationship("Company", back_populates="vacancies")
    candidates = relationship("Candidate", back_populates="vacancy")

class Candidate(Base):
    __tablename__ = "candidates"
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String)
    last_name = Column(String)
    email = Column(String)
    phone = Column(String, nullable=True)
    telegram_id = Column(String, nullable=True)
    resume_text = Column(Text)
    ai_score = Column(Float, default=0.0)
    ai_summary = Column(Text, nullable=True)
    status = Column(String, default="new")
    source = Column(String, default="manual")
    
    vacancy_id = Column(Integer, ForeignKey("vacancies.id"))
    vacancy = relationship("Vacancy", back_populates="candidates")
    
    # Важно: кандидат тоже принадлежит компании!
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    company = relationship("Company", back_populates="candidates")
    
    created_at = Column(DateTime, default=datetime.utcnow)