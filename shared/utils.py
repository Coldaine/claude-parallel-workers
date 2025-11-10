"""Utility functions for the parallel hooks system."""

import os
import uuid
import platform
from pathlib import Path
from datetime import datetime
from typing import Optional


def generate_run_id() -> str:
    """Generate a unique run ID.

    Returns:
        A short, unique run ID (e.g., R42a3)
    """
    # Use last 4 chars of UUID for brevity
    short_id = str(uuid.uuid4())[-4:]
    return f"R{short_id}"


def get_claude_base_directory() -> Path:
    """Get the base Claude directory.

    Returns:
        Path to .claude directory
    """
    # Check if CLAUDE_PROJECT_DIR is set (we're in a hook)
    if 'CLAUDE_PROJECT_DIR' in os.environ:
        return Path(os.environ['CLAUDE_PROJECT_DIR']) / '.claude'

    # Otherwise use current working directory
    return Path.cwd() / '.claude'


def get_run_directory(run_id: str) -> Path:
    """Get the directory for a specific run.

    Args:
        run_id: The run identifier

    Returns:
        Path to the run directory
    """
    base = get_claude_base_directory()
    return base / 'runs' / run_id


def ensure_directory(path: Path) -> Path:
    """Ensure a directory exists.

    Args:
        path: Path to create if it doesn't exist

    Returns:
        The path that was created/verified
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_current_run_id() -> Optional[str]:
    """Get the current run ID from environment or state file.

    Returns:
        Current run ID or None if not in a run
    """
    # Check environment variable first
    if 'CLAUDE_RUN_ID' in os.environ:
        return os.environ['CLAUDE_RUN_ID']

    # Check for state file
    state_file = get_claude_base_directory() / 'current_run.txt'
    if state_file.exists():
        return state_file.read_text().strip()

    return None


def set_current_run_id(run_id: str) -> None:
    """Set the current run ID in state file.

    Args:
        run_id: Run ID to set as current
    """
    state_file = get_claude_base_directory() / 'current_run.txt'
    ensure_directory(state_file.parent)
    state_file.write_text(run_id)


def clear_current_run_id() -> None:
    """Clear the current run ID."""
    state_file = get_claude_base_directory() / 'current_run.txt'
    if state_file.exists():
        state_file.unlink()


def is_windows() -> bool:
    """Check if running on Windows.

    Returns:
        True if on Windows platform
    """
    return platform.system() == 'Windows'


def get_python_executable() -> str:
    """Get the path to the Python executable.

    Returns:
        Path to python executable
    """
    import sys
    return sys.executable


def format_timestamp() -> str:
    """Get current timestamp in ISO format.

    Returns:
        ISO formatted timestamp string
    """
    return datetime.now().isoformat()


def sanitize_path(path: str) -> str:
    """Sanitize a file path to prevent directory traversal.

    Args:
        path: Path to sanitize

    Returns:
        Sanitized path
    """
    # Remove any .. components
    path = os.path.normpath(path)

    # Remove leading slashes/backslashes
    while path.startswith(('/', '\\')):
        path = path[1:]

    # Ensure path doesn't escape
    if '..' in path:
        raise ValueError(f"Invalid path: {path}")

    return path


def parse_json_input() -> dict:
    """Parse JSON input from stdin.

    Returns:
        Parsed JSON data from stdin
    """
    import sys
    import json

    input_data = sys.stdin.read()
    if not input_data:
        return {}

    try:
        return json.loads(input_data)
    except json.JSONDecodeError:
        return {}


def output_json(data: dict, exit_code: int = 0) -> None:
    """Output JSON to stdout and exit with specified code.

    Args:
        data: Data to output as JSON
        exit_code: Exit code (0=success, 2=block)
    """
    import sys
    import json

    print(json.dumps(data, indent=2))
    sys.exit(exit_code)


def output_text(text: str, exit_code: int = 0) -> None:
    """Output text to stdout and exit.

    Args:
        text: Text to output
        exit_code: Exit code
    """
    import sys

    print(text)
    sys.exit(exit_code)


def output_error(error: str, exit_code: int = 2) -> None:
    """Output error to stderr and exit.

    Args:
        error: Error message
        exit_code: Exit code (default 2 for blocking)
    """
    import sys

    print(error, file=sys.stderr)
    sys.exit(exit_code)