"""Typed errors for repository input preparation."""


class RepositoryInputError(Exception):
    """Base error for all repository input preparation failures."""


class InvalidRepositorySourceError(RepositoryInputError):
    """Source is not a valid repository path, ZIP, or GitHub URL."""


class RepositorySourceNotFoundError(RepositoryInputError):
    """Source path or URL does not point to a resolvable resource."""


class UnsafeArchiveError(RepositoryInputError):
    """ZIP archive contains unsafe entries (traversal, absolute paths, etc.)."""


class ArchiveLimitExceededError(RepositoryInputError):
    """ZIP archive exceeds configured safety limits."""


class GitUnavailableError(RepositoryInputError):
    """Git executable is not available on the system."""


class GitCloneError(RepositoryInputError):
    """Git clone or checkout failed."""


class UnsupportedRepositoryUrlError(RepositoryInputError):
    """URL format is not a supported repository URL."""


class WorkspaceCleanupError(RepositoryInputError):
    """Failed to clean up the owned workspace."""
