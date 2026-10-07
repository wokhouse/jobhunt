"""jobhunt: pluggable job-board fetcher + keyword/LLM match pipeline."""
__version__ = "0.2.0"

from .models import Job  # noqa: F401
from .registry import (  # noqa: F401
    register_board,
    register_filter,
    register_judge,
)
