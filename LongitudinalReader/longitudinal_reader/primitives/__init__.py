"""The three deterministic primitives — the grounding contract.

They compute the numbers the LLM is not allowed to invent: a slope, a recurrence
count, a constellation match. A finding without a dated receipt from one of these
(or from explicit dated events) is dropped downstream.
"""

from .constellation import match_constellations
from .recurrence import find_recurrences
from .slope import detect_slopes

__all__ = ["detect_slopes", "find_recurrences", "match_constellations"]
