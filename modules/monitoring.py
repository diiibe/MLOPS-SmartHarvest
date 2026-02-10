import time
import json
import os
from datetime import datetime


class PipelineMonitor:
    def __init__(self, project_name, pipeline_type="CORE"):
        self.project_name = project_name
        self.pipeline_type = pipeline_type
        self.start_time = time.time()
        self.end_time = None
        self.steps = []
        self._current_step = None
        self._step_start = None

    def start_step(self, name):
        """Start tracking a new step."""
        if self._current_step:
            self.stop_step(self._current_step)

        self._current_step = name
        self._step_start = time.time()

    def stop_step(self, name, metrics=None):
        """Stop tracking the current step and record metrics."""
        if self._current_step != name:
            # If name mismatch, find if it was already started or just stop current
            pass

        if self._step_start:
            duration = time.time() - self._step_start
            self.steps.append(
                {
                    "name": name,
                    "duration_sec": round(duration, 3),
                    "metrics": metrics or {},
                }
            )

        self._current_step = None
        self._step_start = None

    def save(self, output_dir):
        """Finalize and save the monitoring log."""
        self.end_time = time.time()
        total_duration = self.end_time - self.start_time

        log_data = {
            "project": self.project_name,
            "pipeline": self.pipeline_type,
            "timestamp": datetime.now().isoformat(),
            "duration_total_sec": round(total_duration, 3),
            "steps": self.steps,
        }

        filename = f"monitoring_{self.pipeline_type.lower()}.json"
        path = os.path.join(output_dir, filename)

        try:
            os.makedirs(output_dir, exist_ok=True)
            with open(path, "w") as f:
                json.dump(log_data, f, indent=4)
            print(f"[Monitor] Log saved to: {path}")
        except Exception as e:
            print(f"[Monitor] Warning: Could not save log: {e}")

        return path
