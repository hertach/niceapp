# app/models/patient.py
import datetime
from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Patient(Base):
    __tablename__ = 'patients'

    id:               Mapped[int]                  = mapped_column(primary_key=True)
    first_name:       Mapped[str]                  = mapped_column(String(64))
    last_name:        Mapped[str]                  = mapped_column(String(64))
    date_of_birth:    Mapped[datetime.date | None] = mapped_column(Date, nullable=True)

    # '' | 'm' | 'f' | 'divers'
    gender:           Mapped[str]                  = mapped_column(String(16), default='')

    # Contact
    phone:            Mapped[str]                  = mapped_column(String(32),  default='')
    email:            Mapped[str]                  = mapped_column(String(128), default='')

    # Address
    street:           Mapped[str]                  = mapped_column(String(128), default='')
    postal_code:      Mapped[str]                  = mapped_column(String(16),  default='')
    city:             Mapped[str]                  = mapped_column(String(64),  default='')

    # Insurance
    insurance_name:   Mapped[str]                  = mapped_column(String(128), default='')
    insurance_number: Mapped[str]                  = mapped_column(String(64),  default='')

    # General
    notes:            Mapped[str]                  = mapped_column(Text, default='')
    is_active:        Mapped[bool]                 = mapped_column(default=True)
    created_at:       Mapped[datetime.datetime]    = mapped_column(default=datetime.datetime.utcnow)

    # Optional: assign to a specific therapist (multi-practice)
    therapist_id:     Mapped[int | None]           = mapped_column(ForeignKey('users.id'), nullable=True)

    @property
    def full_name(self) -> str:
        return f'{self.first_name} {self.last_name}'

    def __repr__(self) -> str:
        return f'<Patient {self.full_name}>'