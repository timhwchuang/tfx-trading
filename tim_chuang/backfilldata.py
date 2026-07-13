from __future__ import annotations

import argparse
import csv
import logging
from datetime import datetime, timedelta, timezone

from shioaji import Shioaji

from config_loader import load_config
from shioaji_api import ShioajiAPI


class BackfillData:
    def run(self, api: ShioajiAPI) -> None:
        start_date, end_date = self.parse_date()
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
                writer.writerow(
                    ["timestamp", "open", "high", "low", "close", "volume", "amount"]
                )
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

    def parse_ymd(self, s: str) -> datetime:
        return datetime.strptime(s, "%Y-%m-%d")

    def parse_date(self) -> tuple[datetime, datetime]:
        parser = argparse.ArgumentParser()
        parser.add_argument("--start_date", type=self.parse_ymd, required=True)
        parser.add_argument("--end_date", type=self.parse_ymd, required=True)
        args = parser.parse_args()
        if args.start_date > args.end_date:
            raise ValueError("start_date must be before end_date")
        return args.start_date, args.end_date


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    shioaji = Shioaji(simulation=config.simulation)
    with ShioajiAPI(shioaji=shioaji, config=config) as shioaji_api:
        backfilldata = BackfillData()
        backfilldata.run(shioaji_api)


if __name__ == "__main__":
    main()
