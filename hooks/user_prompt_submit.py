#!/usr/bin/env python3
"""
UserPromptSubmit hook - detects parallelizable tasks and spawns orchestrator.

This hook analyzes user prompts for patterns like:
- "Process files A, B, and C"
- "Analyze modules X, Y, Z"
- "Run tests on components 1, 2, 3"

If detected, it spawns an orchestrator process to coordinate parallel execution.
"""

import sys
import json
import re
import subprocess
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.utils import generate_run_id


def detect_parallel_pattern(prompt: str) -> dict:
    """
    Detect parallelizable patterns in user prompts.

    Returns:
        dict with 'parallelizable' bool and 'items' list if detected
    """
    # Pattern 1: "files A, B, and C" or "files A B C"
    file_pattern = r'files?\s+([A-Za-z0-9_\-\.]+(?:[\s,]+(?:and\s+)?[A-Za-z0-9_\-\.]+)+)'

    # Pattern 2: "modules X, Y, Z"
    module_pattern = r'modules?\s+([A-Za-z0-9_\-\.]+(?:[\s,]+(?:and\s+)?[A-Za-z0-9_\-\.]+)+)'

    # Pattern 3: "components 1, 2, 3"
    component_pattern = r'components?\s+([A-Za-z0-9_\-\.]+(?:[\s,]+(?:and\s+)?[A-Za-z0-9_\-\.]+)+)'

    patterns = [
        (file_pattern, 'file'),
        (module_pattern, 'module'),
        (component_pattern, 'component')
    ]

    for pattern, item_type in patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            # Extract items
            items_str = match.group(1)
            items = re.split(r'[,\s]+(?:and\s+)?', items_str)
            items = [item.strip() for item in items if item.strip()]

            if len(items) >= 2:  # Need at least 2 items for parallelization
                return {
                    'parallelizable': True,
                    'type': item_type,
                    'items': items
                }

    return {'parallelizable': False}


def main():
    """Hook entry point."""
    # Read prompt from stdin (passed by Claude Code)
    try:
        input_data = sys.stdin.read()
        if input_data:
            data = json.loads(input_data)
            prompt = data.get('prompt', '')
        else:
            # If no JSON, treat entire stdin as prompt
            prompt = input_data
    except json.JSONDecodeError:
        # Fallback: treat stdin as raw prompt
        prompt = sys.stdin.read()

    # Detect parallel pattern
    result = detect_parallel_pattern(prompt)

    if result['parallelizable']:
        # Generate run ID
        run_id = generate_run_id()

        # Output status message that will be injected into context
        items = result['items']
        print(f"✨ Parallel execution detected: {len(items)} {result['type']}s")
        print(f"   Items: {', '.join(items)}")
        print(f"   Run ID: {run_id}")
        print()
        print(f"💡 Tip: The orchestrator will coordinate parallel workers for each {result['type']}.")
        print(f"   Track progress in: ~/.claude/runs/{run_id}/")
        print()

        # Note: In a full implementation, we would:
        # 1. Create a tasks.yaml file from the detected items
        # 2. Spawn the orchestrator in the background
        # 3. Store run_id for PostToolUse hook to read
        #
        # For now, just inject informational context

    # Exit 0 to continue normally (don't block)
    sys.exit(0)


if __name__ == "__main__":
    main()
