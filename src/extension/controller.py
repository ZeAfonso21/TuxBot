"""Adapters for the original Actor/Speculator scheduler and LLM transport."""
import json
import time
from optimizer.dual_loop_optimizer import SimpleDualLoopOptimizer
from optimizer.tuners.llm import LLMTuner


class ScopedTuner(LLMTuner):
    def _create_base_prompt(self):
        coordinated = self.config._extension_runtime.coordinated
        role = ('Optimize both co-located applications on this shared Linux host. Reason about contention and trade-offs. '
                'You may change each application cgroup and the allowlisted host-wide controls.' if coordinated else
                'Optimize this application using only its allowlisted cgroup controls.')
        return (role + '\nPreserve hard bounds before considering priorities. Among acceptable configurations seek '
                'default-relative improvement; priorities favor higher-priority applications only when bounds are met. '
                'Exploration can regress performance but do not needlessly harm an objective. '
                'Return JSON with application_updates, host_updates, and reasoning. No commands or paths. '
                'Only change controls in the supplied schema; an empty update is allowed. '
                f'Your loop role is {self.agent_type}. Reasoning chooses a durable configuration; quick reacts to recent evidence.')

    def _create_update_message(self, metrics, current_params, iteration, best_reward=0,
                               history=None, baseline_index=0, aggregation_interval_s=None, **kwargs):
        runtime = self.config._extension_runtime
        entries = history or []
        latest = metrics.extra_metrics.get('extension_observation') if metrics else None
        if latest is None and entries:
            latest = entries[-1].get('metrics', {}).get('extension_observation')
        return json.dumps(dict(iteration=iteration, observation=latest or runtime.baseline,
                               controls=runtime.manager.snapshot(), available_controls=runtime.manager.schema(),
                               recent_measurements=entries[-10:], recent_decisions=runtime.decisions[-20:],
                               final_freeze=kwargs.get('final_freeze_request', False)), allow_nan=False)

    def _get_top_n_summary(self, n=3, history=None):
        return ''  # Legacy scalar reward must not rank multi-objective configurations.

    def _build_response_schema(self):
        runtime = self.config._extension_runtime

        def properties(controls):
            result = {}
            for name, control in controls.items():
                if control.kind == 'integer':
                    result[name] = dict(type='integer', minimum=control.minimum, maximum=control.maximum)
                else:
                    result[name] = dict(type='string', description=control.schema()['format'])
            return dict(type='object', properties=result, additionalProperties=False)

        return dict(type='object', properties={
            'application_updates': dict(type='object', properties={a: properties(c) for a, c in runtime.manager.applications.items()}, additionalProperties=False),
            'host_updates': properties(runtime.manager.host),
            'reasoning': dict(type='string')}, required=['application_updates', 'host_updates', 'reasoning'], additionalProperties=False)

    def _parse_structured_response(self, data):
        self.config._extension_runtime.manager.validate(data)
        return data, data.get('reasoning'), []

    def _parse_response(self, text):
        from .controls import decode
        return self._parse_structured_response(decode(text))

    def _call_llm_with_retries(self, *args, **kwargs):
        # Parse the raw JSON ourselves so duplicate keys cannot disappear in SDK decoding.
        from .controls import decode
        result = list(super()._call_llm_with_retries(*args, **kwargs))
        if result[0]:
            result[1] = decode(result[0])
        elif result[1] is not None:
            raise ValueError('Raw JSON required for duplicate-key validation')
        return tuple(result)

    def generate_gist(self, history):
        return None, None  # No extra paid end-of-session call.


class ScopedController(SimpleDualLoopOptimizer):
    def _execute_window_simple(self, iteration):
        # Legacy helper swallows missing windows. Extension observations must be complete.
        self.current_window_start_time = time.time()
        return self.benchmark.execute_window(window_number=iteration, duration=self.config.window_duration)

    def _measure_default_baseline_window(self):
        # Three synchronized default windows have already been measured by the runner.
        runtime = self.config._extension_runtime
        self.history.append(dict(iteration=0, parameters=runtime.manager.snapshot(),
                                 metrics={'extension_observation': runtime.baseline}, reward=1.0,
                                 pre_tuning_default_config=True, post_tuning_phase=False))
        self.current_parameters = runtime.manager.snapshot()

    def _apply_tuner_response(self, response, agent_name):
        if not response or not response.parameters:
            raise ValueError('No validated scoped proposal returned')
        runtime = self.config._extension_runtime
        with self.parameters_lock:
            decision = dict(timestamp=time.time(), role=agent_name, proposal=response.parameters,
                            response_time=response.response_time, token_metrics=response.token_metrics)
            runtime.decisions.append(decision)
            try:
                self.current_parameters = runtime.manager.apply(response.parameters)
            except Exception as exc:
                decision['error'] = str(exc)
                raise
            decision['effective'] = self.current_parameters
            return time.time()

    def _record_trial(self, entry):
        # Sustained regression is distinct from user constraints. No automatic restoration:
        # stale in-flight requests would immediately overwrite it without scheduler changes.
        runtime = self.config._extension_runtime
        observation = entry.get('metrics', {}).get('extension_observation', {})
        bad = any(a.get('significant_regression', False) for a in observation.get('applications', {}).values())
        runtime.bad_windows = runtime.bad_windows + 1 if bad else 0
        entry['sustained_regression'] = runtime.bad_windows >= runtime.regression_windows
        super()._record_trial(entry)

    def _finish(self, reason):
        # Do not restore while another independent controller is still measuring.
        # Wait for provider threads so no delayed callback can write after runner restoration.
        self.running = False
        self._clear_pending_tuner_requests()
        self.quick_executor.shutdown(wait=True, cancel_futures=True)
        self.reasoning_executor.shutdown(wait=True, cancel_futures=True)
        if reason != 'completed':
            self.benchmark.broker.abort()
        return super()._finish(reason)
