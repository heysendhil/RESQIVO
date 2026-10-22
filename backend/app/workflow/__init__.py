"""LangGraph review workflow: grounded guidance plus deterministic plan validation.

The deterministic validator is authoritative. The model only produces text; it
never calls tools, takes external actions, or decides whether a plan is valid.
"""
