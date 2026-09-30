#!/usr/bin/env python3
"""Emit the Oracle golden replay and realistic final answer as ATIF."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


# Overridable: solve.sh runs from a writable copy of /solution.
SOLUTION_DIR = Path(os.environ.get('SOLUTION_DIR', '/solution'))
LOG_PATH = Path('/logs/agent/trajectory.json')


def main() -> None:
    golden = json.loads((SOLUTION_DIR / 'golden_trajectory.json').read_text())
    final_answer = (SOLUTION_DIR / 'final_answer.md').read_text().strip()
    now = datetime.now(timezone.utc).isoformat()
    steps = []
    for index, step in enumerate(golden, start=1):
        execution = step.get('tool_execution_results') or {}
        arguments = execution.get('resolved_arguments') or step.get('arguments') or step.get('args') or {}
        result = execution.get('result')
        observation = {'results': []}
        if result is not None:
            observation['results'].append({'content': json.dumps(result, default=str)})
        steps.append({
            'step_id': index,
            'timestamp': now,
            'source': 'agent',
            'message': f"Oracle replayed {step.get('server', '')}.{step.get('name') or step.get('tool') or ''}".strip('.'),
            'tool_calls': [{'tool_call_id': f'oracle-step-{index}', 'function_name': step.get('name') or step.get('tool') or '', 'arguments': arguments}],
            'observation': observation,
        })
    steps.append({
        'step_id': len(steps) + 1,
        'timestamp': now,
        'source': 'agent',
        'message': 'Finished.',
        'tool_calls': [{'tool_call_id': 'oracle-finish', 'function_name': 'finish', 'arguments': {'message': final_answer}}],
        'observation': {'results': []},
    })
    # Full ATIF envelope, not a bare {steps}: `harbor view` reads
    # trajectory.agent.model_name and errors without it.
    trajectory = {
        'schema_version': 'ATIF-v1.5',
        'session_id': 'oracle-replay',
        'agent': {
            'name': 'oracle',
            'version': '1.0.0',
            'model_name': None,
            'model_provider': None,
        },
        'steps': steps,
    }
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(json.dumps(trajectory, indent=2) + '\n')


if __name__ == '__main__':
    main()
