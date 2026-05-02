from sqlalchemy import Column, String, Float, DateTime, Integer, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class CA(Base):
    __tablename__ = "cas"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Client(Base):
    __tablename__ = "clients"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ca_id = Column(String, ForeignKey("cas.id"), nullable=False)
    name = Column(String, nullable=False)
    gstin = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class ClientData(Base):
    __tablename__ = "client_data"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = Column(String, ForeignKey("clients.id"), nullable=False)
    fy_year = Column(String, nullable=False)
    gstr1_total_sales = Column(Float, nullable=True)
    itr_total_turnover = Column(Float, nullable=True)
    banking_avg_balance = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Score(Base):
    __tablename__ = "scores"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = Column(String, ForeignKey("clients.id"), nullable=False)
    total_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Report(Base):
    __tablename__ = "reports"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = Column(String, ForeignKey("clients.id"), nullable=False)
    advisory = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)