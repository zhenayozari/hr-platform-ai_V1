from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime, Boolean, Float
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    
    # Поля профиля
    description = Column(Text, nullable=True)
    website = Column(String, nullable=True)
    contact_email = Column(String, nullable=True)
    contact_phone = Column(String, nullable=True)
    address = Column(String, nullable=True)
    
    # Связи
    users = relationship("User", back_populates="company")
    vacancies = relationship("Vacancy", back_populates="company")
    candidates = relationship("Candidate", back_populates="company")
    pipeline_stages = relationship("PipelineStage", back_populates="company", order_by="PipelineStage.order")
    email_templates = relationship("EmailTemplate", back_populates="company")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    role = Column(String, default="recruiter")
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
    
    # --- НОВЫЕ ПОЛЯ ---
    salary_min = Column(Integer, nullable=True)
    salary_max = Column(Integer, nullable=True)
    experience = Column(String, nullable=True) # junior, middle, senior, no_exp
    employment_type = Column(String, nullable=True) # full_time, part_time, remote
    city = Column(String, nullable=True)
    # ------------------
    
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
    
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    company = relationship("Company", back_populates="candidates")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    comments = relationship("CandidateComment", back_populates="candidate", order_by="desc(CandidateComment.created_at)")
    activities = relationship("CandidateActivity", back_populates="candidate", order_by="desc(CandidateActivity.created_at)")

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
    created_at = Column(DateTime, default=datetime.utcnow)
    candidate = relationship("Candidate", back_populates="activities")

class PipelineStage(Base):
    __tablename__ = "pipeline_stages"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    key = Column(String, nullable=False)
    label = Column(String, nullable=False)
    color = Column(String, default="#3B82F6")
    order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    is_final = Column(Boolean, default=False)
    company = relationship("Company", back_populates="pipeline_stages")

class EmailTemplate(Base):
    __tablename__ = "email_templates"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    type = Column(String, nullable=False)
    name = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    company = relationship("Company", back_populates="email_templates")