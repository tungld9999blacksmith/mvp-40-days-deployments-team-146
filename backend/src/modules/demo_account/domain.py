"""Demo account state (a single row): when the shared account was last reset."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, SmallInteger
from sqlmodel import Field, SQLModel

STATE_ID = 1


class DemoAccountState(SQLModel, table=True):
    __tablename__ = "demo_account_state"

    id: int = Field(default=STATE_ID, sa_column=Column(SmallInteger, primary_key=True, autoincrement=False))
    last_reset_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
