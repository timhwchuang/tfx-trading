from __future__ import annotations

import argparse
import csv
import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from shioaji import Shioaji

from tfx_trading.config_loader import load_config
from tfx_trading.shioaji_api import ShioajiAPI

_FETCH_SLEEP_S = 0.15


class BackfillData:
    def run(
        self,
        api: ShioajiAPI,
        start_date: datetime,
        end_date: datetime,
        *,
        overwrite: bool = False,
        sleep: Callable[[float], None] = time.sleep,
        sleep_s: float = _FETCH_SLEEP_S,
    ) -> None:
        api.kbars_path().mkdir(parents=True, exist_ok=True)
        current_date = start_date
        while current_date.date() <= end_date.date():
            filename = api.kbars_path() / f"TMFR1_kbars_{current_date:%Y-%m-%d}.csv"
            if filename.exists() and not overwrite:
                current_date += timedelta(days=1)
                continue

            kbars = api.kbars(
                contract=api.get_contract(),
                start=f"{current_date:%Y-%m-%d}",
                end=f"{current_date:%Y-%m-%d}",
            )
            sleep(sleep_s)

            if len(kbars.ts) == 0:
                current_date += timedelta(days=1)
                continue

            zipped = zip(
                kbars.ts,
                kbars.Open,
                kbars.High,
                kbars.Low,
                kbars.Close,
                kbars.Volume,
                kbars.Amount,
                strict=True,
            )

            with filename.open("w", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(["timestamp", "open", "high", "low", "close", "volume", "amount"])
                for timestamp, open, high, low, close, volume, amount in zipped:
                    dt = datetime.fromtimestamp(timestamp / 1000000000, tz=timezone.utc)
                    writer.writerow(
                        [
                            f"{dt:%Y-%m-%d %H:%M:%S.%f}",
                            open,
                            high,
                            low,
                            close,
                            volume,
                            amount,
                        ]
                    )
            current_date += timedelta(days=1)

        print("Backfill data completed")


def parse_ymd(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill data")
    parser.add_argument("--start_date", type=parse_ymd, required=True, help="YYYY-MM-DD")
    parser.add_argument("--end_date", type=parse_ymd, required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-fetch even when the daily CSV already exists",
    )
    parsed_args = parser.parse_args(args)
    if parsed_args.start_date > parsed_args.end_date:
        raise ValueError("start_date must be before end_date")
    return parsed_args


def parse_date(args: list[str] | None = None) -> tuple[datetime, datetime]:
    parsed_args = parse_args(args)
    return parsed_args.start_date, parsed_args.end_date


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parsed_args = parse_args()
    config = load_config()
    shioaji = Shioaji(simulation=config.simulation)
    with ShioajiAPI(shioaji=shioaji, config=config) as shioaji_api:
        backfilldata = BackfillData()
        backfilldata.run(
            shioaji_api,
            parsed_args.start_date,
            parsed_args.end_date,
            overwrite=parsed_args.overwrite,
        )


if __name__ == "__main__":
    main()
