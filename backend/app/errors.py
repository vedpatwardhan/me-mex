class ImmutableNodeViolation(Exception):
    """Raised when a write targets immutable ROOT evidence or CONCEPT_I."""


class NotFoundError(Exception):
    """Entity missing in Mongo."""


class ValidationError(Exception):
    """Invalid tool arguments or graph state."""
