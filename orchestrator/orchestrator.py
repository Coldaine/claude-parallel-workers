#!/usr/bin/env python3
"""
Orchestrator for parallel task execution.
Combines ZO's asyncio pattern with SQLite event store.
"""

import asyncio
import sys
import yaml
from pathlib import Path
from typing import List, Dict, Set
from dataclasses import dataclass
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.models import Task, Worker, Plan, EventType
from shared.event_store_v2 import EventStoreV2
from shared.utils import generate_run_id, get_run_directory


@dataclass
class TaskDefinition:
    """Task definition from YAML."""
    name: str
    command: str
    prompt: str = ""
    dependencies: List[str] = None
    timeout: int = 300

    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []


class Orchestrator:
    """Main orchestrator for parallel task execution."""

    def __init__(self, tasks_file: Path):
        self.tasks_file = tasks_file
        self.run_id = generate_run_id()
        self.run_dir = get_run_directory(self.run_id)
        self.run_dir.mkdir(parents=True, exist_ok=True)

        # Initialize event store
        db_path = self.run_dir / "events.db"
        self.store = EventStoreV2(str(db_path))

        # Load tasks
        self.task_defs = self._load_tasks()
        self.batches = []
        self.workers = {}

    def _load_tasks(self) -> List[TaskDefinition]:
        """Load tasks from YAML file."""
        with open(self.tasks_file) as f:
            data = yaml.safe_load(f)

        tasks = []
        for task_data in data.get('tasks', []):
            tasks.append(TaskDefinition(
                name=task_data['name'],
                command=task_data.get('command', ''),
                prompt=task_data.get('prompt', ''),
                dependencies=task_data.get('dependencies', []),
                timeout=task_data.get('timeout', 300)
            ))

        return tasks

    def _validate_dependencies(self):
        """Validate that all dependencies exist."""
        task_names = {t.name for t in self.task_defs}

        for task in self.task_defs:
            for dep in task.dependencies:
                if dep not in task_names:
                    raise ValueError(f"Task '{task.name}' depends on unknown task '{dep}'")

    def _resolve_dependencies(self) -> List[List[TaskDefinition]]:
        """
        Resolve task dependencies using topological sort.
        Returns batches of tasks that can execute in parallel.
        """
        batches = []
        completed = set()
        task_map = {t.name: t for t in self.task_defs}

        while len(completed) < len(self.task_defs):
            # Find tasks whose dependencies are all completed
            ready = []
            for task in self.task_defs:
                if task.name not in completed:
                    if all(dep in completed for dep in task.dependencies):
                        ready.append(task)

            if not ready:
                raise ValueError("Circular dependency detected in tasks")

            batches.append(ready)
            completed.update(t.name for t in ready)

        return batches

    def _create_plan(self):
        """Create execution plan and store in database."""
        tasks = []
        for batch_idx, batch in enumerate(self.batches):
            for task_def in batch:
                task = Task(
                    id=task_def.name,
                    description=task_def.prompt or task_def.command,
                    dependencies=task_def.dependencies,
                    inputs={},
                    outputs={},
                    worker_hint=None
                )
                tasks.append(task)

        plan = Plan(
            run_id=self.run_id,
            created_at=datetime.now(),
            prompt=f"Executing {len(tasks)} tasks from {self.tasks_file.name}",
            tasks=tasks,
            workers=[]
        )

        # Store plan in database
        self.store.create_plan(
            run_id=self.run_id,
            prompt=plan.prompt,
            tasks=[t.__dict__ for t in tasks]
        )

    async def _spawn_worker(self, task_def: TaskDefinition) -> str:
        """Spawn a worker process for a task."""
        worker_id = f"W-{task_def.name}"

        # Create worker record
        self.store.create_worker(
            worker_id=worker_id,
            run_id=self.run_id,
            task_id=task_def.name
        )

        # Emit start event
        self.store.append_event(
            run_id=self.run_id,
            worker_id=worker_id,
            event_type=EventType.START.value,
            task_id=task_def.name,
            payload={"command": task_def.command, "prompt": task_def.prompt}
        )

        # Update worker status
        self.store.update_worker_status(
            worker_id=worker_id,
            state="busy",
            progress=0,
            last_message=f"Starting task: {task_def.name}"
        )

        return worker_id

    async def _execute_task(self, task_def: TaskDefinition, worker_id: str) -> Dict:
        """Execute a single task."""
        try:
            # Create worker directory
            worker_dir = self.run_dir / "workers" / worker_id
            worker_dir.mkdir(parents=True, exist_ok=True)

            # Build command
            cmd = task_def.command
            if task_def.prompt:
                # If there's a prompt, we'd invoke Claude Code here
                # For now, just execute the command
                cmd = f'echo "Task: {task_def.name}" && {cmd}'

            # Execute command with timeout
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(worker_dir)
            )

            # Wait with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=task_def.timeout
                )

                success = proc.returncode == 0

                # Store output
                output_file = worker_dir / "output.txt"
                output_file.write_text(stdout.decode())

                if stderr:
                    error_file = worker_dir / "error.txt"
                    error_file.write_text(stderr.decode())

                # Emit events
                if success:
                    self.store.append_event(
                        run_id=self.run_id,
                        worker_id=worker_id,
                        event_type=EventType.ARTIFACT.value,
                        task_id=task_def.name,
                        payload={"path": str(output_file)}
                    )

                    self.store.append_event(
                        run_id=self.run_id,
                        worker_id=worker_id,
                        event_type=EventType.DONE.value,
                        task_id=task_def.name,
                        payload={"success": True}
                    )

                    self.store.update_worker_status(
                        worker_id=worker_id,
                        state="done",
                        progress=100,
                        last_message="Completed successfully"
                    )
                else:
                    error_msg = stderr.decode() if stderr else "Command failed"
                    self.store.append_event(
                        run_id=self.run_id,
                        worker_id=worker_id,
                        event_type=EventType.ERROR.value,
                        task_id=task_def.name,
                        payload={"error": error_msg}
                    )

                    self.store.update_worker_status(
                        worker_id=worker_id,
                        state="error",
                        progress=0,
                        last_message=error_msg
                    )

                return {
                    "task": task_def.name,
                    "worker": worker_id,
                    "success": success,
                    "output": stdout.decode(),
                    "error": stderr.decode() if stderr else None
                }

            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()

                error_msg = f"Task timed out after {task_def.timeout}s"
                self.store.append_event(
                    run_id=self.run_id,
                    worker_id=worker_id,
                    event_type=EventType.ERROR.value,
                    task_id=task_def.name,
                    payload={"error": error_msg}
                )

                self.store.update_worker_status(
                    worker_id=worker_id,
                    state="error",
                    progress=0,
                    last_message=error_msg
                )

                return {
                    "task": task_def.name,
                    "worker": worker_id,
                    "success": False,
                    "error": error_msg
                }

        except Exception as e:
            error_msg = f"Exception: {str(e)}"
            self.store.append_event(
                run_id=self.run_id,
                worker_id=worker_id,
                event_type=EventType.ERROR.value,
                task_id=task_def.name,
                payload={"error": error_msg}
            )

            self.store.update_worker_status(
                worker_id=worker_id,
                state="error",
                progress=0,
                last_message=error_msg
            )

            return {
                "task": task_def.name,
                "worker": worker_id,
                "success": False,
                "error": error_msg
            }

    async def _execute_batch(self, batch: List[TaskDefinition]) -> List[Dict]:
        """Execute a batch of tasks in parallel."""
        # Spawn workers
        workers = []
        for task_def in batch:
            worker_id = await self._spawn_worker(task_def)
            workers.append((task_def, worker_id))

        # Execute all tasks in parallel using asyncio.gather
        tasks = [
            self._execute_task(task_def, worker_id)
            for task_def, worker_id in workers
        ]

        results = await asyncio.gather(*tasks)
        return results

    async def execute(self):
        """Execute all tasks."""
        print(f"🚀 Starting run {self.run_id}")
        print(f"📁 Working directory: {self.run_dir}")
        print()

        # Validate and resolve dependencies
        self._validate_dependencies()
        self.batches = self._resolve_dependencies()

        print(f"📋 Execution Plan:")
        for i, batch in enumerate(self.batches, 1):
            print(f"  Batch {i}: {len(batch)} tasks")
            for task in batch:
                deps = f" (depends on: {', '.join(task.dependencies)})" if task.dependencies else ""
                print(f"    - {task.name}{deps}")
        print()

        # Create plan
        self._create_plan()

        # Execute batches sequentially, tasks within batch in parallel
        all_results = []
        for batch_idx, batch in enumerate(self.batches, 1):
            print(f"⚡ Executing Batch {batch_idx} ({len(batch)} tasks in parallel)...")

            results = await self._execute_batch(batch)
            all_results.extend(results)

            # Print batch results
            success_count = sum(1 for r in results if r['success'])
            print(f"  ✓ {success_count}/{len(results)} tasks succeeded")
            print()

        # Print summary
        total_success = sum(1 for r in all_results if r['success'])
        print(f"📊 Summary:")
        print(f"  Total tasks: {len(all_results)}")
        print(f"  Successful: {total_success}")
        print(f"  Failed: {len(all_results) - total_success}")
        print()
        print(f"💾 Results stored in: {self.run_dir}")

        return all_results


async def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: orchestrator.py <tasks.yaml>")
        sys.exit(1)

    tasks_file = Path(sys.argv[1])
    if not tasks_file.exists():
        print(f"Error: Tasks file not found: {tasks_file}")
        sys.exit(1)

    orchestrator = Orchestrator(tasks_file)
    await orchestrator.execute()


if __name__ == "__main__":
    asyncio.run(main())
