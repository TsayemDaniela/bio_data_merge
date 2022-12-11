"""Database types models."""
from enum import IntEnum

class DatabaseType(IntEnum):
    """Database Types."""
    BioGRID = 0
    IntAct = 1
    STRING = 2