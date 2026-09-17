class SofaError(Exception):
    """Base class for Sofa pipeline errors."""
    pass

class ProviderError(SofaError):
    """Error from the provider."""
    pass

class CircuitOpenError(SofaError):
    """Circuit breaker is open."""
    pass
