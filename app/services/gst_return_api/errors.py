class GSTAPIError(RuntimeError):
    """Base error for GST Return API integration."""


class GSTAPIConfigError(GSTAPIError):
    """Raised when required GST API environment configuration is missing."""


class GSTAPIRemoteError(GSTAPIError):
    """Raised when the GST API provider responds with an error or is unavailable."""


class GSTSessionExpired(GSTAPIError):
    """Raised when GST auth token is missing or expired."""
