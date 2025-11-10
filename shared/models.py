"""Data models for the parallel hooks system."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional
import json


class EventType(Enum):
    """Types of events that workers can emit."""
    START = "start"
    PROGRESS = "progress"
    ARTIFACT = "artifact"
    ERROR = "error"
    DONE = "done"
    MERGE_READY = "merge_ready"


class WorkerState(Enum):
    """States a worker can be in."""
    INIT = "init"
    RUNNING = "running"
    WAITING = "waiting"
    ERROR = "error"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Event:
    """Represents an event in the system."""
    t: EventType  # event type
    ts: str  # ISO timestamp
    w: Optional[str] = None  # worker ID
    task: Optional[str] = None  # task ID
    msg: Optional[str] = None  # message
    path: Optional[str] = None  # artifact path
    pct: Optional[int] = None  # progress percentage
    error: Optional[Dict[str, Any]] = None  # error details
    artifacts: Optional[List[str]] = None  # list of artifacts

    def to_json(self) -> str:
        """Convert event to JSON string for events.jsonl."""
        data = {
            't': self.t.value if isinstance(self.t, EventType) else self.t,
            'ts': self.ts
        }
        # Add optional fields only if they have values
        if self.w is not None:
            data['w'] = self.w
        if self.task is not None:
            data['task'] = self.task
        if self.msg is not None:
            data['msg'] = self.msg
        if self.path is not None:
            data['path'] = self.path
        if self.pct is not None:
            data['pct'] = self.pct
        if self.error is not None:
            data['error'] = self.error
        if self.artifacts is not None:
            data['artifacts'] = self.artifacts
        return json.dumps(data, separators=(',', ':'))

    @classmethod
    def from_json(cls, json_str: str) -> 'Event':
        """Create an Event from a JSON string."""
        data = json.loads(json_str)
        return cls(
            t=EventType(data['t']) if 't' in data else EventType.START,
            ts=data.get('ts', datetime.now().isoformat()),
            w=data.get('w'),
            task=data.get('task'),
            msg=data.get('msg'),
            path=data.get('path'),
            pct=data.get('pct'),
            error=data.get('error'),
            artifacts=data.get('artifacts')
        )


@dataclass
class Task:
    """Represents a task to be executed."""
    id: str
    description: str
    deps: List[str] = field(default_factory=list)
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    worker_hint: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary."""
        return asdict(self)


@dataclass
class Worker:
    """Represents a worker process."""
    id: str
    task: str
    cmd: List[str]
    state: WorkerState = WorkerState.INIT
    pid: Optional[int] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    progress: int = 0
    last_msg: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert worker to dictionary."""
        data = asdict(self)
        if isinstance(data.get('state'), WorkerState):
            data['state'] = data['state'].value
        return data


@dataclass
class Plan:
    """Represents an execution plan."""
    run_id: str
    created_at: str
    prompt: str
    tasks: List[Task]
    workers: List[Worker]

    def to_dict(self) -> Dict[str, Any]:
        """Convert plan to dictionary for JSON serialization."""
        return {
            'run_id': self.run_id,
            'created_at': self.created_at,
            'prompt': self.prompt,
            'tasks': [t.to_dict() for t in self.tasks],
            'workers': [w.to_dict() for w in self.workers]
        }

    def to_json(self) -> str:
        """Convert plan to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Plan':
        """Create a Plan from a dictionary."""
        return cls(
            run_id=data['run_id'],
            created_at=data['created_at'],
            prompt=data['prompt'],
            tasks=[Task(**t) for t in data['tasks']],
            workers=[Worker(**w) for w in data['workers']]
        )

    @classmethod
    def from_json(cls, json_str: str) -> 'Plan':
        """Create a Plan from a JSON string."""
        return cls.from_dict(json.loads(json_str))


@dataclass
class Status:
    """Represents the current status of all workers."""
    run_id: str
    workers: List[Dict[str, Any]]
    blocked_on: List[str] = field(default_factory=list)
    merge_ready: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert status to dictionary."""
        return asdict(self)

    def to_compact_string(self) -> str:
        """Generate a compact status string for context injection."""
        parts = [f"R{self.run_id} status —"]

        for worker in self.workers:
            w_id = worker['id']
            state = worker.get('state', 'unknown')
            pct = worker.get('percent', 0)
            msg = worker.get('last_msg', '')

            if state == 'done':
                parts.append(f"{w_id} ✓ done")
            elif state == 'error' or state == 'failed':
                parts.append(f"{w_id} ✗ {state}")
            elif state == 'waiting':
                parts.append(f"{w_id} waiting")
            else:
                parts.append(f"{w_id} {pct}% {msg}")

        if self.merge_ready:
            parts.append("merge: ready")
        elif self.blocked_on:
            parts.append(f"merge: blocked on {', '.join(self.blocked_on)}")
        else:
            parts.append("merge: pending")

        return " ; ".join(parts)