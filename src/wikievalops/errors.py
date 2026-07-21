class WikiEvalError(Exception):
    """WikiEvalOps 可预期业务异常的基类。"""


class DatasetValidationError(WikiEvalError):
    pass


class TraceValidationError(WikiEvalError):
    pass


class ConfigurationError(WikiEvalError):
    pass
