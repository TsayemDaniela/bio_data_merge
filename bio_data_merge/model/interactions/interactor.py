"""Interactor Model."""
from enum import Enum
from pydantic import BaseModel, Extra


class Interactor(BaseModel):
    """Interactor Model."""

    class Config:
        extra = Extra.allow


class InteractorVariant(Enum):
    """Enum for variant of interactor."""

    A = "a"
    B = "b"
