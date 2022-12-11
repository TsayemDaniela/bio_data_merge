"""Interaction Properties Model."""
from pydantic import BaseModel, Extra


class InteractionProperties(BaseModel):
    """Interaction Properties Model."""

    class Config:
        extra = Extra.allow