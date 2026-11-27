"""Experiment configuration and baseline-relative performance (no machine I/O)."""
from dataclasses import dataclass
import math
import re
from statistics import mean, median


def positive(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"Expected a finite positive measurement, got {value!r}")
    return value


@dataclass
class Application:
    id: str
    metric: str
    objective: str
    start: list
    measure: list
    bound: object = "default"
    priority: float = 1
    baseline: float = None
    ready_signal: bool = False

    @classmethod
    def load(cls, data):
        app = cls(**data)
        if app.baseline is not None:
            raise ValueError('Baseline must be measured in the current co-located session')
        if not isinstance(app.metric, str) or not app.metric:
            raise ValueError('metric must be a nonempty measurement key')
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", app.id):
            raise ValueError("Invalid application ID")
        if app.objective not in ("minimize", "maximize"):
            raise ValueError("objective must be minimize or maximize")
        positive(app.priority)
        if type(app.ready_signal) is not bool:
            raise ValueError('ready_signal must be boolean')
        if app.bound != "default":
            positive(app.bound)
        for command in (app.start, app.measure):
            if not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command):
                raise ValueError("Commands must be nonempty argv arrays (never model-generated)")
        return app

    def set_baseline(self, values, aggregation='median'):
        # EXTENSION: opt-in mean preserves historical median experiments.
        if len(values) != 3 or aggregation not in ('mean', 'median'):
            raise ValueError('Baseline requires exactly three windows and mean/median aggregation')
        self.baseline = (mean if aggregation == 'mean' else median)(positive(v) for v in values)

    def observation(self, current, tolerance):
        positive(current)
        positive(self.baseline)
        bound = self.baseline if self.bound == "default" else self.bound
        factor = self.baseline / current if self.objective == "minimize" else current / self.baseline
        violation = current > bound if self.objective == "minimize" else current < bound
        regression = current > self.baseline * (1 + tolerance) if self.objective == "minimize" else current < self.baseline * (1 - tolerance)
        return dict(metric=self.metric, objective=self.objective, baseline=self.baseline,
                    current=current, bound=bound, priority=self.priority, improvement=factor,
                    constraint_violation=violation, significant_regression=regression)
