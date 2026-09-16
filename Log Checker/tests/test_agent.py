import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from aliyun.log import GetLogsResponse, LogException
from aliyun.log.index_config_response import GetIndexResponse

from log_checker.api import SlsReader
from log_checker.cli import check_once, main, read_report
from log_checker.config import AgentError, credentials, load_config, validate
from log_checker.metrics import evaluate, normalize, transition
from log_checker.queries import PRESETS, build_query
from log_checker.storage import load_state, state_key


def metric_row(total=1000, errors=0, **overrides):
    values = {"total": total, "valid_status": total, "server_errors": errors,
              "not_found": 0, "rate_limited": 0, "latency_samples": total,
              "slow_requests": 0, "p95_seconds": 0.2 if total else None}
    return {**values, **overrides}


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(Path(__file__).resolve().parents[1] / "config.example.json")

    def test_missing_credentials_never_print_environment_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            env = {"LOG_CHECKER_ENV_FILE": str(Path(folder) / "absent"),
                   "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "DO-NOT-PRINT-THIS"}
            stream = io.StringIO()
            with patch.dict(os.environ, env, clear=True), redirect_stdout(stream):
                code = main(["doctor"])
            self.assertEqual(code, 2)
            self.assertNotIn("DO-NOT-PRINT-THIS", stream.getvalue())
            self.assertFalse(json.loads(stream.getvalue())["network_checked"])

    def test_do_not_mix_credentials_between_file_and_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            env_file = Path(folder) / ".env"
            env_file.write_text("ALIBABA_CLOUD_ACCESS_KEY_ID=file-id\nALIBABA_CLOUD_ACCESS_KEY_SECRET=file-secret\n")
            with patch.dict(os.environ, {"LOG_CHECKER_ENV_FILE": str(env_file)}, clear=True):
                self.assertEqual(credentials()[:2], ("file-id", "file-secret"))
                with patch.dict(os.environ, {"ALIBABA_CLOUD_ACCESS_KEY_ID": "another-id"}):
                    with self.assertRaises(AgentError):
                        credentials()

    def test_reject_non_https_and_arbitrary_hosts_and_sql_identifiers(self):
        for endpoint in ("http://us-east-1.log.aliyuncs.com", "https://example.com", "https://us-east-1.log.aliyuncs.com.attacker.test"):
            c = copy.deepcopy(self.config)
            c["endpoint"] = endpoint
            with self.assertRaises(ValueError):
                validate(c)
        c = copy.deepcopy(self.config)
        c["fields"]["status"] = 'status";SELECT'
        with self.assertRaises(ValueError):
            validate(c)

    def test_reject_invalid_and_missing_metrics(self):
        for rows in ([], [metric_row(), metric_row()], [metric_row(total=-1)],
                     [metric_row(p95_seconds="nan")], [metric_row(server_errors=1001)],
                     [metric_row(valid_status=0, errors=10)], [{"total": 1}]):
            with self.subTest(rows=rows), self.assertRaises(AgentError):
                normalize(rows)

    def test_low_sample_zero_and_field_gaps_do_not_recover_5xx(self):
        old = {"active": {"server_error_rate": {"rule": "server_error_rate", "severity": "critical"}}}
        previous = normalize([metric_row()])
        for row in (metric_row(total=0), metric_row(total=10), metric_row(valid_status=0)):
            findings, assessed = evaluate(normalize([row]), previous, self.config)
            state, events = transition(old, findings, assessed, "now")
            self.assertIn("server_error_rate", state["active"])
            self.assertFalse(any(e["kind"] == "recovered" for e in events))
            self.assertTrue(findings)

    def test_threshold_boundary_dedup_and_recovery(self):
        current, previous = normalize([metric_row(errors=10)]), normalize([metric_row()])
        findings, assessed = evaluate(current, previous, self.config)
        self.assertEqual([f["rule"] for f in findings], ["server_error_rate"])
        state, first = transition({}, findings, assessed, "first")
        state, repeated = transition(state, findings, assessed, "repeat")
        healthy, checked = evaluate(previous, previous, self.config)
        state, recovery = transition(state, healthy, checked, "last")
        self.assertEqual([e["kind"] for e in first], ["opened"])
        self.assertEqual(repeated, [])
        self.assertEqual([e["kind"] for e in recovery], ["recovered"])
        self.assertEqual(state["active"], {})

    def test_adjacent_windows_have_no_overlap_and_delay(self):
        fake = Mock()
        fake.query.return_value = {"rows": [metric_row()], "request_id": "fixture"}
        with patch("log_checker.cli.time.time", return_value=100000):
            report = read_report(self.config, fake)
        a, b = fake.query.call_args_list
        self.assertEqual(a.args[1:3], (98980, 99880))
        self.assertEqual(b.args[1:3], (98080, 98980))
        self.assertIn("schema_unverified", [f["rule"] for f in report["findings"]])

    def make_reader(self):
        with patch("log_checker.api.credentials", return_value=("fake-id", "fake-secret", "", "test")):
            return SlsReader(self.config)

    def sdk_response(self, rows, progress="Complete"):
        return GetLogsResponse({"data": rows, "meta": {"progress": progress, "count": len(rows)}},
                               {"x-log-requestid": "TEST-ID"})

    def test_real_sdk_request_and_response_contract(self):
        reader = self.make_reader()
        self.assertEqual(reader.client.http_type, "https://")
        self.assertEqual(reader.client.timeout, 20)
        with patch.object(reader.client, "get_logs", return_value=self.sdk_response([metric_row()])) as call:
            result = reader.query(build_query(self.config), 1000, 1900, 1)
        request = call.call_args.args[0]
        self.assertEqual((request.get_project(), request.get_logstore()), ("example-logs", "example-site"))
        self.assertEqual((request.get_from(), request.get_to(), request.get_line()), (1000, 1900, 1))
        self.assertFalse(request.get_power_sql())
        self.assertEqual(result["request_id"], "TEST-ID")
        self.assertEqual(normalize(result["rows"])["total"], 1000)

    def test_real_sdk_incomplete_response_is_error(self):
        reader = self.make_reader()
        with patch.object(reader.client, "get_logs", return_value=self.sdk_response([metric_row()], "Incomplete")):
            with self.assertRaises(AgentError) as failure:
                reader.query(build_query(self.config), 1000, 1900)
        self.assertEqual(failure.exception.code, "incomplete_query")

    def test_sdk_errors_omit_messages_headers_and_bodies(self):
        reader = self.make_reader()
        failure = LogException("Unauthorized", "DO-NOT-PRINT-MESSAGE", "safe-request-id",
                               resp_header="DO-NOT-PRINT-HEADERS", resp_body="DO-NOT-PRINT-BODY")
        with patch.object(reader.client, "get_logs", side_effect=failure):
            with self.assertRaises(AgentError) as raised:
                reader.query(build_query(self.config), 1000, 1900)
        encoded = json.dumps(raised.exception.as_dict())
        self.assertNotIn("DO-NOT-PRINT", encoded)
        self.assertIn("safe-request-id", encoded)

    def test_real_sdk_index_response_contract(self):
        reader = self.make_reader()
        response = GetIndexResponse({"keys": {"status": {"type": "long", "doc_value": True}}},
                                    {"x-log-requestid": "schema-fixture"})
        with patch.object(reader.client, "get_index_config", return_value=response):
            self.assertEqual(reader.schema()["fields"]["status"], {"type": "long", "sql_enabled": True})

    def test_bounded_queries(self):
        reader = self.make_reader()
        for start, end, limit in ((0, 86401, 20), (2, 1, 20), (1, 2, 201), (1, 2, 0)):
            with self.assertRaises(AgentError):
                reader.query("*", start, end, limit)
        for preset in PRESETS:
            sql = build_query(self.config, preset, 12)
            self.assertTrue(sql.startswith("* | SELECT"))
            self.assertIn("LIMIT", sql)

    def test_monitor_full_lifecycle_and_persisted_dedup(self):
        c = copy.deepcopy(self.config)
        c["schema_verified"] = True
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            reader = Mock()
            reader.query.return_value = {"rows": [metric_row(errors=25)], "request_id": "fixture"}
            with patch("log_checker.storage.ROOT", root), patch("log_checker.cli.ROOT", root), \
                 patch("log_checker.cli.SlsReader", return_value=reader), patch("log_checker.cli.time.time", return_value=100000):
                first, code = check_once(c)
                self.assertEqual(code, 1)
                self.assertEqual([e["rule"] for e in first["events"]], ["server_error_rate"])
                repeat, _ = check_once(c)
                self.assertEqual(repeat["status"], "skipped")
                with patch("log_checker.cli.time.time", return_value=100300):
                    reader.query.side_effect = AgentError("incomplete_query", "incomplete")
                    failed, code = check_once(c)
                self.assertEqual(code, 2)
                self.assertEqual({a["rule"] for a in failed["active_alerts"]}, {"server_error_rate", "query_error"})
                self.assertEqual(load_state(c)["last_window_end"], 99600)
                with patch("log_checker.cli.time.time", return_value=100600):
                    reader.query.side_effect = None
                    reader.query.return_value = {"rows": [metric_row()], "request_id": "fixture"}
                    recovered, code = check_once(c)
                self.assertEqual(code, 0)
                self.assertEqual({e["rule"] for e in recovered["events"]}, {"server_error_rate", "query_error"})
                self.assertTrue(all(e["kind"] == "recovered" for e in recovered["events"]))
                self.assertTrue((root / "outputs/latest/report.md").is_file())
                self.assertEqual(len((root / "state" / (state_key(c) + "-events.jsonl")).read_text(encoding="utf-8").splitlines()), 4)

    def test_corrupt_state_is_not_silently_reset(self):
        with tempfile.TemporaryDirectory() as folder, patch("log_checker.storage.ROOT", Path(folder)):
            path = Path(folder) / "state" / (state_key(self.config) + ".json")
            path.parent.mkdir()
            path.write_text("invalid json")
            with self.assertRaises(AgentError):
                load_state(self.config)


if __name__ == "__main__":
    unittest.main()
