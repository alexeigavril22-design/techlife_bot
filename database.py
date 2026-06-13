from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, BigInteger
from sqlalchemy.ext.asyncio import AsyncAttrs, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from config import DATABASE_URL

class Base(AsyncAttrs, DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True)
    full_name = Column(String)
    is_premium = Column(Boolean, default=False)
    premium_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

class Reminder(Base):
    __tablename__ = "reminders"
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger)
    text = Column(String)
    remind_at = Column(DateTime)
    is_active = Column(Boolean, default=True)

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger)
    title = Column(String)
    deadline = Column(DateTime, nullable=True)
    is_done = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)

class Expense(Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger)
    amount = Column(Float)
    category = Column(String)
    comment = Column(String, nullable=True)
    date = Column(DateTime, default=datetime.now)

class Medicine(Base):
    __tablename__ = "medicines"
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger)
    name = Column(String)
    dose = Column(String)
    time = Column(String)
    is_active = Column(Boolean, default=True)

engine = create_async_engine(DATABASE_URL)
async_session = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)