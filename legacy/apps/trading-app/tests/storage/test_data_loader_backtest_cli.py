"""Backtest CLI date-resolution tests (legacy; requires trading-backtest)."""

from __future__ import annotations

# Moved from apps/trading-app/tests/storage/test_data_loader.py during refresh.
class TestBacktestDatesFromCache(unittest.TestCase):
    def test_main_dates_from_cache(self):
        from backtest.__main__ import main

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            dt = datetime.date(2026, 6, 22)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 22, 9), "18000", 1, 0)],
                cache_path(root, "TMFR1", dt),
            )
            with patch("backtest.__main__.BacktestEngine") as engine_cls:
                rc = main(
                    [
                        "--code",
                        "TMFR1",
                        "--dates-from-cache",
                        "--cache-dir",
                        str(root),
                    ]
                )
            self.assertEqual(rc, 0)
            engine_cls.assert_called_once()
            self.assertEqual(engine_cls.call_args[0][1], [dt])

    def test_main_invalid_from_date_exits_1(self):
        from backtest.__main__ import main

        rc = main(
            [
                "--code",
                "TMFR1",
                "--dates",
                "2026-06-22",
                "--from-date",
                "not-a-date",
            ]
        )
        self.assertEqual(rc, 1)

    def test_main_report_invokes_emit_report(self):
        from backtest.__main__ import main

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            dt = datetime.date(2026, 6, 22)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 22, 9), "18000", 1, 0)],
                cache_path(root, "TMFR1", dt),
            )
            with patch("backtest.__main__.BacktestEngine") as engine_cls:
                with patch("backtest.__main__.emit_report") as emit_report:
                    with patch(
                        "backtest.__main__.configure_backtest_session_logging"
                    ) as configure_logging:
                        rc = main(
                            [
                                "--code",
                                "TMFR1",
                                "--dates",
                                "2026-06-22",
                                "--cache-dir",
                                str(root),
                                "--report",
                            ]
                        )
            self.assertEqual(rc, 0)
            engine_cls.assert_called_once()
            emit_report.assert_called_once()
            log_path = emit_report.call_args[0][0]
            self.assertEqual(log_path.name, "backtest_TMFR1_20260622.log")
            json_path = emit_report.call_args.kwargs["json_path"]
            self.assertEqual(json_path.name, "backtest_TMFR1_20260622.json")
            self.assertTrue(emit_report.call_args.kwargs["print_report"])
            configure_logging.assert_called_once()
            self.assertEqual(configure_logging.call_args[0][0], str(log_path))
            self.assertTrue(configure_logging.call_args.kwargs["truncate"])

    def test_main_plain_backtest_uses_log_file_from_config(self):
        from backtest.__main__ import main

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            log_path = root / "uat.log"
            dt = datetime.date(2026, 6, 22)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 22, 9), "18000", 1, 0)],
                cache_path(root, "TMFR1", dt),
            )
            with patch("backtest.__main__.LOG_FILE", str(log_path)):
                with patch("backtest.__main__.BacktestEngine") as engine_cls:
                    with patch("backtest.__main__.configure_backtest_session_logging") as configure_logging:
                        rc = main(
                            [
                                "--code",
                                "TMFR1",
                                "--dates",
                                "2026-06-22",
                                "--cache-dir",
                                str(root),
                            ]
                        )
            self.assertEqual(rc, 0)
            engine_cls.assert_called_once()
            configure_logging.assert_called_once_with(
                str(log_path),
                console_level=None,
                truncate=False,
                level=ANY,
            )

    def test_cache_dir_output_tag_disambiguates_outside_tick_cache(self):
        from backtest.__main__ import _cache_dir_output_tag

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            outside = root / "runA" / "2026_05"
            outside.mkdir(parents=True)
            self.assertEqual(_cache_dir_output_tag(outside), "runA_2026_05")

    def test_default_report_paths_filtered_cache_appends_date_range(self):
        from backtest.__main__ import default_report_paths
        from storage.cache_paths import DEFAULT_TICK_CACHE_DIR

        month_dir = DEFAULT_TICK_CACHE_DIR / "2026_05"
        dates = [datetime.date(2026, 5, 1), datetime.date(2026, 5, 15)]
        log_path, json_path = default_report_paths(
            dates_from_cache=True,
            code="TMFR1",
            dates=dates,
            cache_dir=month_dir,
            date_range_filtered=True,
        )
        self.assertEqual(log_path.name, "backtest_2026_05_20260501_20260515.log")
        self.assertEqual(json_path.name, "backtest_2026_05_20260501_20260515.json")

    def test_main_dates_from_cache_report_uses_cache_dir_name(self):
        from backtest.__main__ import main

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            tick_root = root / "tick_cache"
            month_dir = tick_root / "2026_05"
            month_dir.mkdir(parents=True)
            dt = datetime.date(2026, 5, 2)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 5, 2, 9), "18000", 1, 0)],
                cache_path(month_dir, "TMFR1", dt),
            )
            with patch.dict(os.environ, {"FT003_HOLDOUT_UNSEAL": "1"}):
                with patch("backtest.__main__.DEFAULT_TICK_CACHE_DIR", tick_root):
                    with patch("backtest.__main__.BacktestEngine"):
                        with patch("backtest.__main__.emit_report") as emit_report:
                            with patch(
                                "backtest.__main__.configure_backtest_session_logging"
                            ):
                                rc = main(
                                    [
                                        "--code",
                                        "TMFR1",
                                        "--dates-from-cache",
                                        "--cache-dir",
                                        str(month_dir),
                                        "--report",
                                    ]
                                )
            self.assertEqual(rc, 0)
            emit_report.assert_called_once()
            log_path = emit_report.call_args[0][0]
            json_path = emit_report.call_args.kwargs["json_path"]
            self.assertEqual(log_path.name, "backtest_2026_05.log")
            self.assertEqual(json_path.name, "backtest_2026_05.json")
            self.assertTrue(emit_report.call_args.kwargs["print_report"])

    def test_main_dates_from_cache_default_tick_cache_naming(self):
        from backtest.__main__ import main

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            tick_root = root / "tick_cache"
            tick_root.mkdir()
            dt = datetime.date(2026, 6, 22)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 22, 9), "18000", 1, 0)],
                cache_path(tick_root, "TMFR1", dt),
            )
            with patch("backtest.__main__.DEFAULT_TICK_CACHE_DIR", tick_root):
                with patch("backtest.__main__.BacktestEngine"):
                    with patch("backtest.__main__.emit_report") as emit_report:
                        with patch(
                            "backtest.__main__.configure_backtest_session_logging"
                        ):
                            rc = main(
                                [
                                    "--code",
                                    "TMFR1",
                                    "--dates-from-cache",
                                    "--cache-dir",
                                    str(tick_root),
                                    "--report",
                                ]
                            )
            self.assertEqual(rc, 0)
            emit_report.assert_called_once()
            log_path = emit_report.call_args[0][0]
            json_path = emit_report.call_args.kwargs["json_path"]
            self.assertEqual(log_path.name, "backtest_tick_cache.log")
            self.assertEqual(json_path.name, "backtest_tick_cache.json")

    def test_main_dates_from_cache_filtered_range_suffix(self):
        from backtest.__main__ import main

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            tick_root = root / "tick_cache"
            month_dir = tick_root / "2026_05"
            month_dir.mkdir(parents=True)
            for day in (1, 15):
                dt = datetime.date(2026, 5, day)
                save_ticks_csv(
                    [ReplayTick(datetime.datetime(2026, 5, day, 9), "18000", 1, 0)],
                    cache_path(month_dir, "TMFR1", dt),
                )
            with patch.dict(os.environ, {"FT003_HOLDOUT_UNSEAL": "1"}):
                with patch("backtest.__main__.DEFAULT_TICK_CACHE_DIR", tick_root):
                    with patch("backtest.__main__.BacktestEngine"):
                        with patch("backtest.__main__.emit_report") as emit_report:
                            with patch(
                                "backtest.__main__.configure_backtest_session_logging"
                            ):
                                rc = main(
                                    [
                                        "--code",
                                        "TMFR1",
                                        "--dates-from-cache",
                                        "--cache-dir",
                                        str(month_dir),
                                        "--from-date",
                                        "2026-05-01",
                                        "--to-date",
                                        "2026-05-01",
                                        "--report",
                                    ]
                                )
            self.assertEqual(rc, 0)
            emit_report.assert_called_once()
            log_path = emit_report.call_args[0][0]
            json_path = emit_report.call_args.kwargs["json_path"]
            self.assertEqual(log_path.name, "backtest_2026_05_20260501.log")
            self.assertEqual(json_path.name, "backtest_2026_05_20260501.json")

    def test_main_report_with_custom_log_file_pairs_json_stem(self):
        from backtest.__main__ import main

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            custom_log = root / "custom_run.log"
            dt = datetime.date(2026, 6, 22)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 22, 9), "18000", 1, 0)],
                cache_path(root, "TMFR1", dt),
            )
            with patch("backtest.__main__.BacktestEngine"):
                with patch("backtest.__main__.emit_report") as emit_report:
                    with patch("backtest.__main__.configure_backtest_session_logging"):
                        rc = main(
                            [
                                "--code",
                                "TMFR1",
                                "--dates",
                                "2026-06-22",
                                "--cache-dir",
                                str(root),
                                "--log-file",
                                str(custom_log),
                                "--report",
                            ]
                        )
            self.assertEqual(rc, 0)
            emit_report.assert_called_once()
            log_path = emit_report.call_args[0][0]
            json_path = emit_report.call_args.kwargs["json_path"]
            self.assertEqual(log_path, custom_log)
            self.assertEqual(json_path.name, "custom_run.json")

    def test_session_logging_writes_audits_before_engine_wiring(self):
        from backtest.__main__ import configure_backtest_session_logging
        from trading_engine.logging_setup import shutdown_async_logging

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "backtest.log"
            configure_backtest_session_logging(str(path), truncate=True)
            logging.getLogger("trading_engine").info("SIGNAL_AUDIT smoke")
            shutdown_async_logging()
            text = path.read_text(encoding="utf-8")
            self.assertIn("SIGNAL_AUDIT", text)

    def test_session_logging_overwrites_previous_run(self):
        from backtest.__main__ import configure_backtest_session_logging
        from trading_engine.logging_setup import shutdown_async_logging

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "backtest.log"
            configure_backtest_session_logging(str(path), truncate=True)
            logging.getLogger("trading_engine").info("first-run-marker")
            shutdown_async_logging()
            configure_backtest_session_logging(str(path), truncate=True)
            logging.getLogger("trading_engine").info("second-run-marker")
            shutdown_async_logging()
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("first-run-marker", text)
            self.assertIn("second-run-marker", text)


if __name__ == "__main__":
    unittest.main()
