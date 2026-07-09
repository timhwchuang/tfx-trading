# June 2026 Trader Journal

```
STATUS: Research exploration (2026-06 only)
NOT: Pilot / UAT / Holdout / expectancy claim
Path support ≠ net edge after friction & execution
Blind lock sha16: c5dc921a38fc7e6b
```

## Method

1. Built full-month 15m timeline + long trader_scan seeds.
2. **Phase 1a blind lock**: entry_ts / stop only (no MAE/MFE). File `june_2026_candidates_blind.json`.
3. **Phase 2 score**: 15/30/60/120m (night: 60/120/180/360m). Friction display 5 pts; primary buffer 8 pts.
4. OSF foil not re-run this pass (known miss on trend-day A / flush C).

## Regime map summary

- `trend_up`: 4 days
- `night_drive`: 4 days
- `trend_down`: 4 days
- `flush_short`: 4 days
- `transition`: 4 days
- `flush_long`: 1 days

See `june_regime_map.md` for per-day rows.

## Candidates by day

### 2026-06-01 — `trend_up` (gap gap_up +390, net +657, rng 1064)

- **L-2026-06-01-A** long `A` @ `06-01T09:50` entry=46092.0 stop=45930.0 → **PATH_OK**
  - rationale: Price held above OR high 45960 on 5m after breakout
  - 30m MFE/MAE=123.0/84.0; 60m MFE/MAE=372.0/84.0; edge60=288.0 net−f5=283.0; stop30=False
- **N-2026-06-01-N** long `N` @ `06-02T05:00` entry=46549.0 stop=45720.0 → **STORY_BROKE**
  - rationale: night net +472 over range 994; hold direction into next session research
  - night 120m MFE/MAE=0.0/549.0; 180m MFE/MAE=0.0/549.0; edge~=-549.0; stop30=False

### 2026-06-02 — `night_drive` (gap gap_down -418, net +14, rng 897)

- **L-2026-06-02-C** long `C` @ `06-02T10:35` entry=45882.0 stop=45656.0 → **PATH_WEAK**
  - rationale: 15m swept overnight_low (L45656) reclaimed; 5m closed above sweep high 45822 — momentum continuation without FVG retest
  - 30m MFE/MAE=75.0/215.0; 60m MFE/MAE=75.0/549.0; edge60=-474.0 net−f5=-479.0; stop30=False
- **N-2026-06-02-N** long `N` @ `06-03T05:00` entry=46696.0 stop=46150.0 → **PATH_OK**
  - rationale: night net +456 over range 603; hold direction into next session research
  - night 120m MFE/MAE=198.0/0.0; 180m MFE/MAE=198.0/0.0; edge~=198.0; stop30=False

### 2026-06-03 — `night_drive` (gap gap_up +98, net +84, rng 433)

- **L-2026-06-03-C** long `C` @ `06-03T09:35` entry=46976.0 stop=46678.0 → **STORY_BROKE**
  - rationale: 15m swept or_low (L46678) reclaimed; 5m closed above sweep high 46838 — momentum continuation without FVG retest
  - 30m MFE/MAE=14.0/419.0; 60m MFE/MAE=14.0/419.0; edge60=-405.0 net−f5=-410.0; stop30=True
- **N-2026-06-03-N-** short `N-` @ `06-04T05:00` entry=46540.0 stop=47008.0 → **PATH_OK**
  - rationale: night net -255 over range 638; hold direction into next session research
  - night 120m MFE/MAE=95.0/0.0; 180m MFE/MAE=95.0/0.0; edge~=95.0; stop30=False

### 2026-06-04 — `night_drive` (gap gap_down -47, net -198, rng 443)

- **L-2026-06-04-C** long `C` @ `06-04T11:15` entry=46420.0 stop=46142.0 → **PATH_OK**
  - rationale: 15m swept or_low (L46142) reclaimed; 5m closed above sweep high 46388 — momentum continuation without FVG retest
  - 30m MFE/MAE=165.0/9.0; 60m MFE/MAE=165.0/41.0; edge60=124.0 net−f5=119.0; stop30=False

### 2026-06-05 — `trend_down` (gap gap_down -622, net -430, rng 1118)

- **L-2026-06-05-C** long `C` @ `06-05T10:30` entry=45741.0 stop=44885.0 → **STORY_BROKE**
  - rationale: Gap-down tagged overnight 45481, 15m reclaim + 5m BOS above 45732
  - 30m MFE/MAE=39.0/228.0; 60m MFE/MAE=39.0/336.0; edge60=-297.0 net−f5=-302.0; stop30=False
- **S-2026-06-05-A-** short `A-` @ `06-05T09:30` entry=44940.0 stop=45752.0 → **STORY_BROKE**
  - rationale: h4 not above; 15m broke OR low 45111.0 with bearish close
  - 30m MFE/MAE=6.0/531.0; 60m MFE/MAE=6.0/827.0; edge60=-821.0 net−f5=-826.0; stop30=False

### 2026-06-08 — `flush_short` (gap gap_up +150, net +852, rng 1428)

- **N-2026-06-08-N** long `N` @ `06-09T05:00` entry=44019.0 stop=43185.0 → **STORY_BROKE**
  - rationale: night net +767 over range 1069; hold direction into next session research
  - night 120m MFE/MAE=0.0/484.0; 180m MFE/MAE=0.0/484.0; edge~=-484.0; stop30=False

### 2026-06-09 — `transition` (gap gap_down -326, net +1038, rng 1213)

- **L-2026-06-09-A** long `A` @ `06-09T09:40` entry=44095.0 stop=43925.0 → **PATH_OK**
  - rationale: Price held above OR high 43955 on 5m after breakout
  - 30m MFE/MAE=175.0/73.0; 60m MFE/MAE=263.0/73.0; edge60=190.0 net−f5=185.0; stop30=False
- **N-2026-06-09-N-** short `N-` @ `06-10T05:00` entry=43835.0 stop=45090.0 → **PATH_OK**
  - rationale: night net -865 over range 2692; hold direction into next session research
  - night 120m MFE/MAE=119.0/42.0; 180m MFE/MAE=119.0/42.0; edge~=77.0; stop30=False

### 2026-06-10 — `trend_down` (gap gap_down -56, net -476, rng 1351)

- **N-2026-06-10-N-** short `N-` @ `06-11T05:00` entry=42590.0 stop=43997.0 → **STORY_BROKE**
  - rationale: night net -906 over range 1511; hold direction into next session research
  - night 120m MFE/MAE=0.0/207.0; 180m MFE/MAE=0.0/207.0; edge~=-207.0; stop30=False

### 2026-06-11 — `flush_short` (gap gap_up +53, net +568, rng 1375)

- **L-2026-06-11-C** long `C` @ `06-11T11:10` entry=42800.0 stop=42385.0 → **STORY_BROKE**
  - rationale: 15m swept overnight_low (L42385) reclaimed; 5m closed above sweep high 42733 — momentum continuation without FVG retest
  - 30m MFE/MAE=200.0/297.0; 60m MFE/MAE=434.0/297.0; edge60=137.0 net−f5=132.0; stop30=False
- **S-2026-06-11-A-** short `A-` @ `06-11T10:30` entry=42312.0 stop=43461.0 → **PATH_WEAK**
  - rationale: h4 not above; 15m broke OR low 42616.0 with bearish close
  - 30m MFE/MAE=174.0/421.0; 60m MFE/MAE=174.0/508.0; edge60=-334.0 net−f5=-339.0; stop30=False

### 2026-06-12 — `trend_down` (gap gap_up +542, net -678, rng 898)

- **L-2026-06-12-C** long `C` @ `06-12T10:10` entry=44386.0 stop=44160.0 → **STORY_BROKE**
  - rationale: 15m swept or_low (L44160) reclaimed; 5m closed above sweep high 44378 — momentum continuation without FVG retest
  - 30m MFE/MAE=86.0/165.0; 60m MFE/MAE=86.0/165.0; edge60=-79.0 net−f5=-84.0; stop30=False
- **S-2026-06-12-A-** short `A-` @ `06-12T09:30` entry=44108.0 stop=44958.0 → **STORY_BROKE**
  - rationale: h4 not above; 15m broke OR low 44318.0 with bearish close
  - 30m MFE/MAE=68.0/271.0; 60m MFE/MAE=68.0/329.0; edge60=-261.0 net−f5=-266.0; stop30=False

### 2026-06-15 — `night_drive` (gap gap_up +1005, net -77, rng 565)

- **N-2026-06-15-N** long `N` @ `06-16T05:00` entry=46253.0 stop=45525.0 → **STORY_BROKE**
  - rationale: night net +695 over range 712; hold direction into next session research
  - night 120m MFE/MAE=0.0/349.0; 180m MFE/MAE=0.0/349.0; edge~=-349.0; stop30=False

### 2026-06-16 — `transition` (gap gap_down -87, net -400, rng 727)

- **L-2026-06-16-C** long `C` @ `06-16T09:40` entry=45735.0 stop=45457.0 → **PATH_WEAK**
  - rationale: 15m swept or_low (L45457) reclaimed; 5m closed above sweep high 45715 — momentum continuation without FVG retest
  - 30m MFE/MAE=69.0/90.0; 60m MFE/MAE=69.0/180.0; edge60=-111.0 net−f5=-116.0; stop30=False
- **N-2026-06-16-N-** short `N-` @ `06-17T05:00` entry=45019.0 stop=45963.0 → **STORY_BROKE**
  - rationale: night net -774 over range 988; hold direction into next session research
  - night 120m MFE/MAE=0.0/379.0; 180m MFE/MAE=0.0/379.0; edge~=-379.0; stop30=False

### 2026-06-17 — `trend_up` (gap gap_up +290, net +720, rng 953)

- **no_trade** (no locked candidate)

### 2026-06-18 — `trend_up` (gap gap_up +421, net +270, rng 499)

- **L-2026-06-18-A** long `A` @ `06-18T10:20` entry=46645.0 stop=46533.0 → **STORY_BROKE**
  - rationale: Price held above OR high 46563 on 5m after breakout
  - 30m MFE/MAE=47.0/194.0; 60m MFE/MAE=47.0/301.0; edge60=-254.0 net−f5=-259.0; stop30=True
- **N-2026-06-18-N** long `N` @ `06-19T00:00` entry=47269.0 stop=46701.0 → **PATH_WEAK**
  - rationale: night net +499 over range 564; hold direction into next session research
  - windows incomplete (session gap / missing 1m after entry)

### 2026-06-22 — `trend_up` (gap gap_up +170, net +1025, rng 1110)

- **L-2026-06-22-A** long `A` @ `06-22T09:35` entry=48079.0 stop=47858.0 → **PATH_WEAK**
  - rationale: Price held above OR high 47888 on 5m after breakout
  - 30m MFE/MAE=118.0/214.0; 60m MFE/MAE=245.0/214.0; edge60=31.0 net−f5=26.0; stop30=False
- **N-2026-06-22-N** long `N` @ `06-23T05:00` entry=48888.0 stop=48471.0 → **STORY_BROKE**
  - rationale: night net +350 over range 742; hold direction into next session research
  - night 120m MFE/MAE=0.0/625.0; 180m MFE/MAE=0.0/625.0; edge~=-625.0; stop30=False

### 2026-06-23 — `transition` (gap gap_down -69, net -1382, rng 1397)

- **S-2026-06-23-A-** short `A-` @ `06-23T09:45` entry=48120.0 stop=48827.0 → **PATH_OK**
  - rationale: h4 not above; 15m broke OR low 48263.0 with bearish close
  - 30m MFE/MAE=158.0/139.0; 60m MFE/MAE=158.0/139.0; edge60=19.0 net−f5=14.0; stop30=False
- **N-2026-06-23-N-** short `N-` @ `06-24T05:00` entry=46224.0 stop=47101.0 → **STORY_BROKE**
  - rationale: night net -744 over range 1050; hold direction into next session research
  - night 120m MFE/MAE=0.0/776.0; 180m MFE/MAE=0.0/776.0; edge~=-776.0; stop30=False

### 2026-06-24 — `flush_short` (gap gap_up +557, net -425, rng 1147)

- **L-2026-06-24-C** long `C` @ `06-24T11:35` entry=46226.0 stop=45911.0 → **PATH_WEAK**
  - rationale: 15m swept overnight_low (L45911) reclaimed; 5m closed above sweep high 46221 — momentum continuation without FVG retest
  - 30m MFE/MAE=56.0/140.0; 60m MFE/MAE=56.0/256.0; edge60=-200.0 net−f5=-205.0; stop30=False
- **S-2026-06-24-A-** short `A-` @ `06-24T11:00` entry=46063.0 stop=47078.0 → **PATH_WEAK**
  - rationale: h4 not above; 15m broke OR low 46303.0 with bearish close
  - 30m MFE/MAE=152.0/194.0; 60m MFE/MAE=152.0/233.0; edge60=-81.0 net−f5=-86.0; stop30=False

### 2026-06-25 — `flush_short` (gap gap_up +95, net -443, rng 910)

- **L-2026-06-25-C** long `C` @ `06-25T11:10` entry=46590.0 stop=46296.0 → **STORY_BROKE**
  - rationale: 15m swept or_low (L46296) reclaimed; 5m closed above sweep high 46503 — momentum continuation without FVG retest
  - 30m MFE/MAE=32.0/166.0; 60m MFE/MAE=32.0/210.0; edge60=-178.0 net−f5=-183.0; stop30=False
- **S-2026-06-25-A-** short `A-` @ `06-25T10:15` entry=46233.0 stop=47018.0 → **STORY_BROKE**
  - rationale: h4 not above; 15m broke OR low 46475.0 with bearish close
  - 30m MFE/MAE=145.0/305.0; 60m MFE/MAE=145.0/395.0; edge60=-250.0 net−f5=-255.0; stop30=False

### 2026-06-26 — `trend_down` (gap gap_down -173, net -1110, rng 1422)

- **S-2026-06-26-A-** short `A-` @ `06-26T10:00` entry=45284.0 stop=45823.0 → **PATH_WEAK**
  - rationale: h4 not above; 15m broke OR low 45406.0 with bearish close
  - 30m MFE/MAE=115.0/193.0; 60m MFE/MAE=344.0/193.0; edge60=151.0 net−f5=146.0; stop30=False

### 2026-06-29 — `transition` (gap gap_down -195, net +760, rng 1268)

- **L-2026-06-29-A** long `A` @ `06-29T09:50` entry=45552.0 stop=45438.0 → **STORY_BROKE**
  - rationale: Price held above OR high 45468 on 5m after breakout
  - 30m MFE/MAE=11.0/488.0; 60m MFE/MAE=11.0/488.0; edge60=-477.0 net−f5=-482.0; stop30=True
- **N-2026-06-29-N** long `N` @ `06-30T05:00` entry=46365.0 stop=45009.0 → **STORY_BROKE**
  - rationale: night net +805 over range 1435; hold direction into next session research
  - night 120m MFE/MAE=0.0/445.0; 180m MFE/MAE=0.0/445.0; edge~=-445.0; stop30=False

### 2026-06-30 — `flush_long` (gap gap_down -227, net +692, rng 957)

- **L-2026-06-30-A** long `A` @ `06-30T09:35` entry=46583.0 stop=46379.0 → **STORY_BROKE**
  - rationale: Price held above OR high 46409 on 5m after breakout
  - 30m MFE/MAE=2.0/253.0; 60m MFE/MAE=142.0/378.0; edge60=-236.0 net−f5=-241.0; stop30=True
- **N-2026-06-30-N** long `N` @ `07-01T00:00` entry=47281.0 stop=46335.0 → **PATH_WEAK**
  - rationale: night net +586 over range 1013; hold direction into next session research
  - windows incomplete (session gap / missing 1m after entry)

## Path-OK subset (7)

- L-2026-06-01-A long A edge60=288.0 (trend_up) — Price held above OR high 45960 on 5m after breakout
- N-2026-06-02-N long N edge60=198.0 (night_drive) — night net +456 over range 603; hold direction into next session research
- N-2026-06-03-N- short N- edge60=95.0 (night_drive) — night net -255 over range 638; hold direction into next session research
- L-2026-06-04-C long C edge60=124.0 (night_drive) — 15m swept or_low (L46142) reclaimed; 5m closed above sweep high 46388 — momentum continuation withou
- L-2026-06-09-A long A edge60=190.0 (transition) — Price held above OR high 43955 on 5m after breakout
- N-2026-06-09-N- short N- edge60=77.0 (night_drive) — night net -865 over range 2692; hold direction into next session research
- S-2026-06-23-A- short A- edge60=19.0 (transition) — h4 not above; 15m broke OR low 48263.0 with bearish close

## Aggregate kills

- **C|long** n=9 support=11% med_edge60=-178.0 kills=['median_path_edge_60m_lt_friction_buffer_8'] primary_eligible=False
- **N|long** n=8 support=12% med_edge60=-464.5 kills=['median_path_edge_60m_lt_friction_buffer_8'] primary_eligible=False
- **A-|short** n=7 support=14% med_edge60=-250.0 kills=['median_path_edge_60m_lt_friction_buffer_8'] primary_eligible=False
- **A|long** n=6 support=33% med_edge60=-102.5 kills=['median_path_edge_60m_lt_friction_buffer_8', 'stop_hit_30m_gt_35pct'] primary_eligible=False
- **N-|short** n=5 support=40% med_edge60=-207.0 kills=['median_path_edge_60m_lt_friction_buffer_8'] primary_eligible=False

## Trader takeaway (honest)

- Month is **two-sided**: strong trend-up early (6/1–3, 6/17–22) and violent trend-down mid (6/5–12, 6/23–26).
- Mechanical long OR-hold (A) and flush-reclaim (C) **mostly fail path checks** in this month once MAE is measured — not just OSF FVG friction.
- A few **individual** path-OK events exist (6/1 A, 6/4 C, 6/9 A, 6/2 night N, 6/23 short) but **no story family** clears primary kill criteria (n, median edge≥8, stop@30).
- Night tags need session-hold research; many are stop-far and path-negative after open.

