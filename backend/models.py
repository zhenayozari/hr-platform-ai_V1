from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime, Boolean, Float
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    users = relationship("User", back_populates="company")
    vacancies = relationship("Vacancy", back_populates="company")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String)
    company_id = Column(Integer, ForeignKey("companies.id"))
    company = relationship("Company", back_populates="users")

class Vacancy(Base):
    __tablename__ = "vacancies"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(Text)
    requirements = Column(Text)
    status = Column(String, default="active")
    company_id = Column(Integer, ForeignKey("companies.id"))
    company = relationship("Company", back_populates="vacancies")
    candidates = relationship("Candidate", back_populates="vacancy")

class Candidate(Base):
    __tablename__ = "candidates"
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String)
    last_name = Column(String)
    email = Column(String)
    phone = Column(String, nullable=True)  # НОВОЕ
    telegram_id = Column(String, nullable=True)
    resume_text = Column(Text)
    ai_score = Column(Float, default=0.0)
    ai_summary = Column(Text, nullable=True)
    status = Column(String, default="new")
    source = Column(String, default="manual")  # НОВОЕ (hh.ru, telegram, manual)
    vacancy_id = Column(Integer, ForeignKey("vacancies.id"))
    vacancy = relationship("Vacancy", back_populates="candidates")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow) # НОВОЕ
    
    # Связи для Пункта 5
    comments = relationship("CandidateComment", back_populates="candidate", order_by="desc(CandidateComment.created_at)")
    activities = relationship("CandidateActivity", back_populates="candidate", order_by="desc(CandidateActivity.created_at)")

# НОВЫЕ ТАБЛИЦЫ ДЛЯ ПУНКТА 5
class CandidateComment(Base):
    __tablename__ = "candidate_comments"
    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"))
    author_name = Column(String)
    text = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    candidate = relationship("Candidate", back_populates="comments")

class CandidateActivity(Base):
    __tablename__ = "candidate_activities"
    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"))
    action = Column(String)
    description = Column(Text)
    old_value = Column(String, nullable=True)
    new_value = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    candidate = relationship("Candidate", back_populates="activities")