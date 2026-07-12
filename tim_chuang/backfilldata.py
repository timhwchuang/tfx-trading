from __future__ import annotations

from shioaji_api import ShioajiAPI
from datetime import datetime, timezone, timedelta
import argparse
import csv

class BackfillData:
    def __init__(self, shioaji_api: ShioajiAPI) -> None:
        self.api = shioaji_api

    def run(self) -> None:
        start_date, end_date = self.parse_date()

        try:
            self.api.login()

            current_date = start_date
            while current_date.date() <= end_date.date():
                kbars = self.api.kbars(contract=self.api.get_contract(), start=f"{current_date:%Y-%m-%d}", end=f"{current_date:%Y-%m-%d}")

                if len(kbars.ts) == 0:
                    current_date += timedelta(days=1)
                    continue

                zipped = zip(kbars.ts, kbars.Open, kbars.High, kbars.Low, kbars.Close, kbars.Volume, kbars.Amount)
                filename = self.api.kbar_path() / f"TMFR1_kbars_{current_date:%Y-%m-%d}.csv"

                with filename.open("w", newline="") as file:
                    writer = csv.writer(file)
                    writer.writerow(["timestamp", "open", "high", "low", "close", "volume", "amount"])
                    for timestamp, o, h, l, c, v, a in zipped:
                        dt = datetime.fromtimestamp(timestamp / 1000000000, tz=timezone.utc)
                        writer.writerow([f"{dt:%Y-%m-%d %H:%M:%S.%f}", o, h, l, c, v, a])
                current_date += timedelta(days=1)

            print("Backfill data completed")
        except Exception as e:
            print(e)
        finally:
            self.api.logout()
            print("Logout completed")

    def parse_date(self) -> tuple[datetime, datetime]:
        parser = argparse.ArgumentParser()
        parser.add_argument("--start_date", type=str)
        parser.add_argument("--end_date", type=str)
        args = parser.parse_args()
        start_date = args.start_date
        end_date = args.end_date
        try:
            start_date_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_date_dt = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            raise ValueError("start_date and end_date must be in the format of YYYY-MM-DD")
        if start_date_dt > end_date_dt:
            raise ValueError("start_date must be before end_date")
        return start_date_dt, end_date_dt

if __name__ == "__main__":
    backfilldata = BackfillData()
    backfilldata.run()