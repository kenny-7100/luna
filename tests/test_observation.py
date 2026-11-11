"""Exercise persistence and graceful stopping without recording the test runner's screen."""

import json
import subprocess
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from luna.observation import read_json, report, worker, write_json


class ObservationTests(unittest.TestCase):
    def test_worker_persists_event_and_stops(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            session = root / "slice"
            session.mkdir()

            def sensor(*args, **kwargs):
                (session / "stop").touch()
                return subprocess.CompletedProcess(
                    args[0], 0, json.dumps({"app": "Example", "screens": []}), ""
                )

            with patch("luna.observation.subprocess.run", side_effect=sensor):
                worker(root, session, 2, 8)
            state = read_json(session / "state.json")
            self.assertEqual(state["status"], "stopped")
            self.assertEqual(state["samples"], 1)
            event = json.loads((session / "events.jsonl").read_text())
            self.assertEqual(event["app"], "Example")
            self.assertIn("captured_at", event)

    def test_sensor_failure_is_recorded_and_report_is_local(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = root / ".local/observation"
            session = store / "slice"
            session.mkdir(parents=True)
            write_json(store / "current.json", {"session": str(session)})

            def failed_sensor(*args, **kwargs):
                (session / "stop").touch()
                raise subprocess.TimeoutExpired(args[0], 25)

            with patch("luna.observation.subprocess.run", side_effect=failed_sensor):
                worker(root, session, 2, 8)
            self.assertEqual(read_json(session / "state.json")["errors"], 1)
            with redirect_stdout(StringIO()):
                report(root)
            self.assertIn("采集错误", (session / "timeline.md").read_text())


if __name__ == "__main__":
    unittest.main()
