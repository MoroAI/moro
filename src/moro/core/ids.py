import uuid
from datetime import datetime


def new_id(prefix: str) -> str:
    """
    Generate a sortable, human-readable ID.
    Format: {prefix}_{YYYYMMDDHHMMSS}_{4hex}
    Examples:
        proj_20260916123456_a1b2
        src_20260916123456_c3d4
        run_20260916123456_e5f6
    """
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    suffix = uuid.uuid4().hex[:4]
    return f"{prefix}_{timestamp}_{suffix}"
