"""The Longitudinal Reader — a diagnostic agent whose only job is the time axis.

Pipeline:  load -> primitives -> decompose -> (evidence) -> reconcile -> render

The three deterministic primitives (slope, recurrence, constellation) produce the
numbers the model is not allowed to invent; the LLM interprets, hypothesizes, and
exercises restraint. Most patients -> silence. See PLAN_LONGITUDINAL.md.
"""

__version__ = "0.1.0"
