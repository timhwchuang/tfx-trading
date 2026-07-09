"""Basic tests for Phase 3 episode replay (FT-001)."""

import unittest
from pathlib import Path

from reporting.uat_report import (
    compute_episodes,
    parse_decision_audit_line,
    parse_exec_audit_line,
    build_tuning_hints,
    format_episode_timeline,
)


class TestEpisodeReplay(unittest.TestCase):
    def test_parse_decision_and_build_basic(self):
        dec = 'DECISION_AUDIT {"audit_schema_version":1,"event_type":"momentum_armed","ts":1740126120,"episode_id":"20260617-003","direction":"Long"}'
        eps = compute_episodes([dec])
        self.assertEqual(len(eps), 1)
        self.assertEqual(eps[0].episode_id, "20260617-003")
        self.assertEqual(eps[0].direction, "Long")

    def test_parse_exec(self):
        ex = 'EXEC_AUDIT {"audit_schema_version":1,"event_type":"pending_armed","ts":1740126198,"signal_id":"20260617-sig-007","order_id":"OID-991"}'
        e = parse_exec_audit_line(ex)
        self.assertIsNotNone(e)
        self.assertEqual(e.event_type, "pending_armed")

    def test_exec_linked_to_episode_via_signal_id(self):
        lines = [
            'DECISION_AUDIT {"audit_schema_version":1,"event_type":"momentum_armed","ts":100,"episode_id":"20260617-010","direction":"Long"}',
            'SIGNAL_AUDIT {"audit_schema_version":1,"intent":"entry","direction":"Buy","price":21840.0,"ts":120,"episode_id":"20260617-010","signal_id":"20260617-sig-010"}',
            'EXEC_AUDIT {"audit_schema_version":1,"event_type":"pending_armed","ts":121,"signal_id":"20260617-sig-010","order_id":"OID-100"}',
            'EXEC_AUDIT {"audit_schema_version":1,"event_type":"pending_timeout","ts":130,"signal_id":"20260617-sig-010","pending_sec":8}',
        ]
        eps = compute_episodes(lines)
        self.assertEqual(len(eps), 1)
        ep = eps[0]
        exec_events = [ev for ev in ep.events if ev.get("source") == "exec"]
        self.assertEqual(len(exec_events), 2)
        self.assertEqual(
            {ev["event_type"] for ev in exec_events},
            {"pending_armed", "pending_timeout"},
        )
        self.assertEqual(ep.outcome, "pending_timeout")

    def test_pending_cancelled_linked_to_episode(self):
        lines = [
            'DECISION_AUDIT {"audit_schema_version":1,"event_type":"momentum_armed","ts":100,"episode_id":"20260617-011","direction":"Long"}',
            'SIGNAL_AUDIT {"audit_schema_version":1,"intent":"entry","direction":"Buy","price":21840.0,"ts":120,"episode_id":"20260617-011","signal_id":"20260617-sig-011"}',
            'EXEC_AUDIT {"audit_schema_version":1,"event_type":"pending_armed","ts":121,"signal_id":"20260617-sig-011","order_id":"OID-101"}',
            'EXEC_AUDIT {"audit_schema_version":1,"event_type":"pending_cancelled","ts":125,"signal_id":"20260617-sig-011","tag":"intent_cancelled"}',
        ]
        eps = compute_episodes(lines)
        ep = eps[0]
        exec_types = {
            ev["event_type"]
            for ev in ep.events
            if ev.get("source") == "exec"
        }
        self.assertEqual(exec_types, {"pending_armed", "pending_cancelled"})

    def test_position_sync_operational_episode(self):
        lines = [
            'EXEC_AUDIT {"audit_schema_version":1,"event_type":"position_sync","ts":1740130400,"qty_before":0,"qty_after":1,"position_dir":"Long"}',
        ]
        eps = compute_episodes(lines)
        self.assertEqual(len(eps), 1)
        self.assertEqual(eps[0].outcome, "position_sync")
        out = format_episode_timeline(eps)
        self.assertIn("Operational EXEC (position_sync)", out)

    def test_episode_filter_by_id(self):
        # just smoke
        eps = compute_episodes([])
        self.assertEqual(len(eps), 0)

    def test_non_happy_timeout_veto_risk(self):
        lines = [
            'DECISION_AUDIT {"audit_schema_version":1,"event_type":"momentum_armed","ts":100,"episode_id":"20260617-001","direction":"Long","consecutive_timeout_streak":1}',
            'DECISION_AUDIT {"audit_schema_version":1,"event_type":"momentum_timeout","ts":280,"episode_id":"20260617-001","direction":"Long","consecutive_timeout_streak":1}',
            'DECISION_AUDIT {"audit_schema_version":1,"event_type":"momentum_armed","ts":300,"episode_id":"20260617-002","direction":"Long","consecutive_timeout_streak":2}',
            'DECISION_AUDIT {"audit_schema_version":1,"event_type":"trend_veto","ts":350,"episode_id":"20260617-002","direction":"Buy","consecutive_veto_streak":1}',
            'DECISION_AUDIT {"audit_schema_version":1,"event_type":"risk_blocked","ts":400,"block_reason":"min_atr","consecutive_loss":3}',
        ]
        eps = compute_episodes(lines)
        self.assertEqual(len(eps), 3)  # 2 armed + 1 risk pseudo
        outcomes = {e.outcome for e in eps}
        self.assertIn("timeout", outcomes)
        self.assertIn("veto", outcomes)
        self.assertIn("risk_blocked", outcomes)
        # pressure context present even with 0s
        for e in eps:
            if e.outcome in ("timeout", "veto"):
                self.assertIn("consecutive_timeout_streak", e.pressure_context or {})

    def test_structure_veto_episode_outcome(self):
        lines = [
            'DECISION_AUDIT {"audit_schema_version":1,"event_type":"momentum_armed","ts":100,"episode_id":"20260618-001","direction":"Long"}',
            'DECISION_AUDIT {"audit_schema_version":1,"event_type":"structure_veto","ts":150,"episode_id":"20260618-001","direction":"Buy","momentum_dir":"Long","structure_bias":"Short","structure_algo_version":1}',
        ]
        eps = compute_episodes(lines)
        self.assertEqual(len(eps), 1)
        self.assertEqual(eps[0].outcome, "veto")

    def test_build_tuning_hints_with_episodes(self):
        # 5 timeout + 1 entered ; use events for armed count
        eps = []
        for i in range(5):
            eps.append( type('E', (), {
                "episode_id": f"d-{i}",
                "outcome": "timeout",
                "direction": "Long",
                "pressure_context": {"consecutive_timeout_streak": 5},
                "events": [{"event_type": "momentum_armed"}]
            })() )
        eps.append( type('E', (), {
            "episode_id": "d-e",
            "outcome": "entered",
            "direction": "Long",
            "pressure_context": {},
            "events": [{"event_type": "momentum_armed"}]
        })() )
        hints = build_tuning_hints(
            conversion_rate=0.05,
            quick_sl_rate=None,
            slippage={},
            expectancy={},
            near_miss=None,
            cancel_rate=None,
            tick_type=None,
            daily_summaries=[],
            cumulative_risk=None,
            episodes=eps,
        )
        self.assertTrue(any("timeout" in h.lower() for h in hints))

    def test_synthetic_fixture_snapshot(self):
        fixture = Path(__file__).parent.parent / "fixtures" / "synthetic_high_pressure.txt"
        self.assertTrue(fixture.exists())
        lines = fixture.read_text(encoding="utf-8").splitlines()
        eps = compute_episodes(lines)
        self.assertGreaterEqual(len(eps), 4)
        # check has timeout, veto, risk
        outcomes = {e.outcome for e in eps}
        self.assertIn("timeout", outcomes)
        self.assertIn("veto", outcomes)
        self.assertIn("risk_blocked", outcomes)
        # snapshot-like: format produces expected structure
        out = format_episode_timeline(eps)
        self.assertIn("20260617-005", out)
        self.assertIn("pressure_context", out)


if __name__ == "__main__":
    unittest.main()
