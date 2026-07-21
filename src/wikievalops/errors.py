class WikiEvalError(Exception):
    """Base exception for expected WikiEvalOps failures."""


class DatasetValidationError(WikiEvalError):
    pass


class TraceValidationError(WikiEvalError):
    pass


class ConfigurationError(WikiEvalError):
    pass

