from __future__ import annotations

import argparse
import csv
import logging
from datetime import datetime, timedelta, timezone

from shioaji import Shioaji

from tfx_trading.config_loader import load_config
from tfx_trading.shioaji_api import ShioajiAPI


class BackfillData:
    def run(self, api: ShioajiAPI, start_date: datetime, end_date: datetime) -> None:
        current_date = start_date
        while current_date.date() <= end_date.date():
            kbars = api.kbars(
                contract=api.get_contract(),
                start=f"{current_date:%Y-%m-%d}",
                end=f"{current_date:%Y-%m-%d}",
            )

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
            )
            filename = api.kbars_path() / f"TMFR1_kbars_{current_date:%Y-%m-%d}.csv"

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

def parse_date(args: list[str] | None = None) -> tuple[datetime, datetime]:
    parser = argparse.ArgumentParser(description="Backfill data")
    parser.add_argument("--start_date", type=parse_ymd, required=True, help="資料回補的開始日期 (格式: YYYY-MM-DD)")
    parser.add_argument("--end_date", type=parse_ymd, required=True, help="資料回補的結束日期 (格式: YYYY-MM-DD)")
    parsed_args = parser.parse_args(args)
    start_date = parsed_args.start_date
    end_date = parsed_args.end_date
    if start_date > end_date:
        raise ValueError("start_date must be before end_date")
    return start_date, end_date


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    shioaji = Shioaji(simulation=config.simulation)
    with ShioajiAPI(shioaji=shioaji, config=config) as shioaji_api:
        backfilldata = BackfillData()
        backfilldata.run(shioaji_api, *parse_date())


if __name__ == "__main__":
    main()
