"""One bounded Gemini schema request using temporary controls; NEVER applies updates."""
import argparse
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from optimizer.config import SimpleConfig
from .controls import Actuator, Control, decode
from .controller import ScopedTuner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorize-api-call', action='store_true')
    parser.add_argument('--model', default='gemini-3.5-flash-lite')
    parser.add_argument('--independent', action='store_true')
    args = parser.parse_args()
    if not args.authorize_api_call:
        parser.error('Requires explicit --authorize-api-call')
    if not os.getenv('GEMINI_API_KEY'):
        parser.error('GEMINI_API_KEY must be loaded into this remote process')
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        controls = {}
        for app in (('A',) if args.independent else ('A', 'B')):
            path = root / app
            path.write_text('100\n')
            controls[app] = {'cpu.weight': Control(path, 1, 10000)}
        host = root / 'host'
        host.write_text('0\n')
        manager = Actuator(controls, {} if args.independent else {'napi_busy_poll': Control(host, 0, 1000)})
        config = SimpleConfig()
        config.parameter_ranges, config.fixed_parameters = {}, {}
        config.llm_actor_model = config.llm_speculator_model = args.model
        config._extension_runtime = SimpleNamespace(manager=manager, coordinated=not args.independent)
        tuner = ScopedTuner(config, 'quick')
        try:
            text, parsed, latency, _, _, tokens = tuner._call_gemini(
                [tuner._create_base_prompt(), 'This is a schema smoke test only. Return empty application_updates and host_updates objects, and a short reasoning string.'],
                tuner._build_response_schema(), iteration=0,
                request_timeout_seconds=30, max_output_tokens=256, allow_thinking=False)
            proposal = decode(text)
            manager.validate(proposal)
            assert manager.snapshot() == manager.initial
            print(json.dumps(dict(model=tuner.model_name, validated=True, applied=False,
                                  latency_seconds=latency, tokens=tokens, proposal=proposal), indent=2))
        except Exception as exc:
            print(json.dumps({'error': str(exc).replace(os.environ['GEMINI_API_KEY'], '[REDACTED]')}, indent=2))
            raise SystemExit(1)
        finally:
            tuner.client.close()


if __name__ == '__main__':
    main()
