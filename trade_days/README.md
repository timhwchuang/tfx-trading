# Taiwan trading calendar cache

Yearly JSON from [pin-yi Taiwan calendar API](https://api.pin-yi.me/taiwan-calendar/{year}) (`isHoliday` per day).

`backfilldata month` reads `{year}.json` here first; missing years are fetched once and saved. Refresh manually:

```bash
python -c "
import json, time, urllib.request
from pathlib import Path
root = Path('trade_days')
for year in [2022, 2023, 2024, 2025, 2026]:
    req = urllib.request.Request(
        f'https://api.pin-yi.me/taiwan-calendar/{year}',
        headers={'User-Agent': 'tfx-trading-backfilldata/1.0', 'Accept': 'application/json'},
    )
    data = json.loads(urllib.request.urlopen(req, timeout=60).read())
    (root / f'{year}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    time.sleep(0.6)
"
```
