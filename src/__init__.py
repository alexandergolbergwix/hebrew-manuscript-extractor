"""
Hebrew Manuscript Entity Extraction System
A functional, ontology-driven extraction pipeline
"""

__version__ = "1.0.0"
__author__ = "Alexander Goldberg"

from .pipeline import run_extraction_pipeline
from .models.entities import Config

__all__ = ["run_extraction_pipeline", "Config"]
