#!/usr/bin/env python3
"""
Simple integration test for the orchestrator.
Runs the example tasks and verifies execution.
"""

import sys
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator.orchestrator import Orchestrator


async def main():
    """Run integration test."""
    print("=" * 60)
    print("Claude Parallel Hooks - Integration Test")
    print("=" * 60)
    print()

    # Get tasks file
    tasks_file = Path(__file__).parent / "tasks.yaml"

    if not tasks_file.exists():
        print(f"Error: {tasks_file} not found")
        return False

    # Create orchestrator
    print("Initializing orchestrator...")
    orchestrator = Orchestrator(tasks_file)

    # Execute tasks
    print("Starting execution...")
    print()

    try:
        results = await orchestrator.execute()

        # Verify results
        print()
        print("=" * 60)
        print("Test Results")
        print("=" * 60)

        success = all(r['success'] for r in results)

        if success:
            print("✓ All tasks completed successfully!")
            return True
        else:
            print("✗ Some tasks failed")
            failed = [r for r in results if not r['success']]
            for r in failed:
                print(f"  - {r['task']}: {r.get('error', 'Unknown error')}")
            return False

    except Exception as e:
        print(f"✗ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
