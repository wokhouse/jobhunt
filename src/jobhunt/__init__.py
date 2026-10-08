"""jobhunt: pluggable job-board fetcher + keyword/LLM match pipeline."""
__version__ = "0.3.1"

from .models import Job  # noqa: F401
from .registry import (  # noqa: F401
    register_board,
    register_filter,
    register_judge,
    register_source,
)
