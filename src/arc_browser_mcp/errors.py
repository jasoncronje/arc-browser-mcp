class ArcBrowserMCPError(RuntimeError):
    """Base error surfaced to MCP clients."""


class ArcNotRunningError(ArcBrowserMCPError):
    """Raised when a read-only operation would otherwise launch Arc."""


class ArcObjectNotFoundError(ArcBrowserMCPError):
    """Raised when a requested window, Space, or tab id cannot be found."""


class ArcAutomationError(ArcBrowserMCPError):
    """Raised when macOS automation returns an unexpected failure."""
