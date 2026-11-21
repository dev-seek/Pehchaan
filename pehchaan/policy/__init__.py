"""The admission gate: resolvers only PROPOSE facts; this package decides what may touch the transcript."""
from .gate import AdmissionGate
from .second_opinion import SecondOpinion

__all__ = ["AdmissionGate", "SecondOpinion"]
