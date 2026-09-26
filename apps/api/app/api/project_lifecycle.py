"""Process-local lifecycle locks for project mutation and background jobs."""

from collections import defaultdict
from threading import RLock

_project_locks: defaultdict[str, RLock] = defaultdict(RLock)


def project_lifecycle_lock(project_id: str) -> RLock:
    """Serialize job submission with deletion for this single-process service."""
    return _project_locks[project_id]
