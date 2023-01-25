"""Interaction Model."""
from pydantic import BaseModel, Field
from .interactor import Interactor
from .interaction_properties import InteractionProperties


class Interaction(BaseModel):
    """Interaction Model."""

    interactor_a: str = Field(
        ..., description="First interactor in a binary interaction"
    )
    interactor_b: str = Field(
        ..., description="Second interactor in a binary interaction"
    )
    interaction_properties: InteractionProperties = Field(
        ..., description="Interaction properties"
    )
