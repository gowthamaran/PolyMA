# PolyMA Lab

PolyMA Lab is a local-first, paper-only research application for one question:

> After a completed green 15-minute Polymarket outcome-token candle closes
> above the previous-candle MA7 but below the previous-candle MA25, with unusual
> volume, is the **next completed 15-minute candle** more likely to be red?

It discovers markets, reconstructs candles from public Polymarket data,
backtests threshold variants, forward-paper-trades signals, grades the exact
next candle, and displays the evidence in a dark FastAPI dashboard.

**The 90% win-rate claim is only a hypothesis. PolyMA never displays it as a
fact unless measured results support it.**

## Safety boundary

PolyMA Lab:

- requires no wallet, private key, seed phrase, Polymarket login, or Funding
  Predicts credential;
- contains no real order submission implementation;
- never automates Funding Predicts or its UI;
- never uses Selenium, Playwright, click simulation, or bot-detection bypasses;
- implements only virtual positions;
- makes every live execution method throw `LiveTradingDisabledError`.

`PaperExecutionProvider` is the only working execution provider. This is a
research system, not financial advice and not a promise of profitability.

## Strategy definition

For completed candle `i`, indicators use candles **strictly before `i`**:

```text
MA7(i)  = mean(close[i-7 : i])
MA25(i) = mean(close[i-25 : i])
AVG_VOLUME_20(i) = mean(volume[i-20 : i])
VOLUME_RATIO(i)  = volume[i] / AVG_VOLUME_20(i)
```

A RED prediction is generated when all are true:

1. `close[i] > open[i]`
2. `close[i] > MA7(i)`
3. `close[i] < MA25(i)`
4. `VOLUME_RATIO(i) > configured threshold` (default `1.50`)

The exact candle at `timestamp[i] + 900 seconds` is graded only after it closes:

- `next_close < next_open` → WIN
- `next_close > next_open` → LOSS
- equal → NEUTRAL
- missing exact next bucket → INVALID in historical analysis, not silently
  replaced by a later candle

Neutral results are excluded from the win-rate denominator and reported
separately.

## Zero-lookahead guarantee

The signal candle must be complete. `MAStrategy.evaluate()` filters history to
timestamps before the current candle and passes only that historical slice to
MA and average-volume functions. The current close is compared with the MAs but
is not included in either MA. Future changes cannot modify an existing signal.

Automated tests deliberately mutate future candle prices and volume, inject a
future candle into history, and change the current close. The historical MA
values and original signal remain unchanged.

## Official data sources

PolyMA uses documented, public, read-only interfaces:

| Purpose | Interface | Endpoint family |
|---|---|---|
| Asset-aware discovery | Gamma tags and market keyset | `gamma-api.polymarket.com/tags/slug/...`, `/markets/keyset` |
| Market metadata/token IDs | Gamma | `/markets/{id}` |
| Actual public trades | Data API | `data-api.polymarket.com/trades` |
| Sampled price history | CLOB | `clob.polymarket.com/prices-history` |
| Executable book snapshots | CLOB | `clob.polymarket.com/book` |

The provider uses official Bitcoin/Ethereum/Solana/XRP tag metadata first and
text inference only as a fallback. It retries transient errors with exponential
backoff, rejects malformed rows, filters token IDs, de-duplicates trade
fingerprints, and paginates within the documented offset cap.

### Volume policy

The CLOB price-history response contains timestamp and price only. It is **not
OHLCV**. PolyMA therefore applies this policy:

- Data API `size` values aggregated by UTC bucket → `REAL_TRADE_VOLUME`
- CLOB sampled price fallback → volume `NULL`, `UNAVAILABLE`, price source
  `SAMPLED_PRICE_PROXY`
- no-trade periods → no fabricated candle

The volume filter cannot pass when volume is unavailable. For clearly separated
price-only research, run `--disable-volume-filter`; those signals use the
`volume-disabled` variant and never mix with volume-enabled results.

Because empty buckets are not fabricated, the default strategy also requires
25 contiguous prior 15-minute buckets. Thin markets may correctly produce zero
signals.

## Installation

Requires Python 3.11 or newer.

```bash
git clone https://github.com/gowthamaran/PolyMA.git
cd PolyMA
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py stats
```

No secret is needed for Polymarket data or paper trading.

## Quick commands

```bash
# Discover active tagged crypto markets
python main.py discover --asset BTC
python main.py discover --asset ETH --limit 100
python main.py discover --all-supported

# Historical research
python main.py backtest --asset BTC --days 90
python main.py backtest --asset BTC --asset ETH --days 90
python main.py backtest --asset BTC --days 180 --walk-forward
python main.py backtest --market MARKET_ID --days 90

# Explicit price-only research when true volume is unavailable
python main.py backtest --asset BTC --days 90 --disable-volume-filter

# One forward cycle, then continuous forward paper testing
python main.py scan --asset BTC --once
python main.py scan --all-supported

# Dashboard and summaries
python main.py dashboard
python main.py stats

# Exports
python main.py export candles
python main.py export signals
python main.py export trades
python main.py export backtests

# Destructive only to virtual account/trades; preserves evidence tables
python main.py reset-paper --yes
```

## Historical testing

The backtester runs all configured thresholds independently:

```text
1.00x, 1.25x, 1.50x, 1.75x, 2.00x, 2.50x, 3.00x
```

Signals from different variants share an `observation_id` but have unique
variant IDs. Database uniqueness is based on market, token, candle timestamp,
variant, and run. Re-running an experiment never turns one observation into
multiple live signals.

Time is split without shuffling:

- oldest 60% → DEVELOPMENT
- middle 20% → VALIDATION
- newest 20% → TEST

Choose parameters using development/validation only. Do not choose the best
threshold using TEST and then call that TEST result unbiased. Reports display
in-sample and out-of-sample results separately.

`--walk-forward` uses a 30-day research window and 7-day forward window by
default. Override with `--train-days` and `--test-days`.

## Baselines and statistics

Every backtest calculates:

- any next candle red;
- next candle red after any green candle;
- green plus close above MA7;
- green plus `MA7 < close < MA25`;
- full volume-filter variants;
- Wilson 95% confidence interval;
- expected directional return, profit factor, maximum drawdown, streaks, and a
  Sharpe-like descriptive metric;
- a seeded random-timestamp sampling check.

The randomization check is exploratory, not proof of causality. A report is
`SUPPORTED` only when at least 100 decisive held-out observations exist and the
held-out Wilson interval is entirely above 50%. Otherwise it is `NOT SUPPORTED`
or `INCONCLUSIVE` under the documented rule.

## Directional test versus paper profitability

Mode A asks only whether the next candle is red.

Mode B simulates buying the complementary outcome. When an observed
complementary ask is available at signal time, it is used. Historical fallback
uses the explicitly labelled approximation `1 - target token price`, then
penalizes entry/exit with configured spread, slippage, fees, and delay. This is
not a claimed fill.

Accuracy can be high while expected value is negative. Treat these as separate
questions.

## Dashboard

Start it with:

```bash
python main.py dashboard
```

Open `http://127.0.0.1:8000`. Sections include overview, latest scanner
candles, signal history, paper trades, markets, threshold comparison,
historical runs, and sanitized settings. Telegram secrets and environment
values are never returned by the API.

For a VPS, keep `APP_HOST=127.0.0.1` and place an authenticated HTTPS reverse
proxy in front of it. Setting `APP_HOST=0.0.0.0` exposes port 8000 directly and
is not recommended without a firewall/authentication layer.

## Telegram alerts

Create a bot with BotFather, obtain your chat ID, then edit `.env`:

```dotenv
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

Restart the scanner. Tokens remain in `.env`, which is ignored by Git. The
dashboard and logs do not display them.

## Restart recovery

Candles and signals use SQLite unique keys. On every cycle the scanner reloads
live PENDING signals and looks for the exact completed next bucket. A process
restart or temporary disconnection cannot legitimately duplicate a signal.
Transient API errors are logged and the continuous loop retries on its next
cycle.

## Ubuntu VPS

After cloning the private repository on the VPS:

```bash
cd PolyMA
chmod +x scripts/install_vps.sh
./scripts/install_vps.sh
```

The installer creates `.venv`, installs dependencies, preserves an existing
`.env`, renders user/path-specific systemd services, and starts both services.

```bash
sudo systemctl status polyma-scanner
sudo systemctl status polyma-dashboard
journalctl -u polyma-scanner -f
sudo systemctl restart polyma-scanner polyma-dashboard
```

To update:

```bash
git pull --ff-only
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
sudo systemctl restart polyma-scanner polyma-dashboard
```

## Tests

```bash
python -m pytest -q
```

Coverage includes indicator math, real-volume aggregation, UTC boundaries,
missing buckets, all strategy conditions, strict volume inequality, disabled
volume labeling, incomplete candles, exact-next grading, neutral/invalid
results, future leakage, chronological splitting, confidence intervals,
database duplicates, repeat experiment isolation, restart grading, virtual P&L,
risk rejection, API retry behavior, and permanent live-execution rejection.

## Logs and exports

- `logs/app.log`
- `logs/scanner.log`
- `logs/errors.log`
- `exports/*.csv`
- `data/polyma.db`

Logs are structured JSON and rotate locally. Secrets are never logged.

## Troubleshooting

**Zero markets:** increase `--limit`; verify the official asset tag exists and
that the VPS can resolve `gamma-api.polymarket.com`.

**Zero candles:** the selected token may have no trades/price observations in
the requested window. This is valid.

**Candles but zero signals:** inspect the dashboard. Thin data may fail the
contiguous-history requirement, or one of the green/MA/volume conditions may be
false. Do not loosen it merely to manufacture results.

**Volume says UNAVAILABLE:** only sampled price history was available. Keep the
volume filter enabled for the original hypothesis or run the explicitly
separate `--disable-volume-filter` experiment.

**429/5xx errors:** the provider uses exponential backoff. Reduce market count
or polling frequency if errors persist.

**Dashboard works locally but not remotely:** this is expected with
`APP_HOST=127.0.0.1`. Use an SSH tunnel or authenticated reverse proxy.

## Current validation status

Automated tests pass. The build workspace successfully inspected current
official Gamma payloads but blocked direct Polymarket DNS from the Python
process, so it did not invent candle, volume, or signal results. See
[`docs/SMOKE_TEST.md`](docs/SMOKE_TEST.md) and rerun the smoke command on the
VPS:

```bash
python main.py smoke-test --asset BTC --limit 2 --hours 48
```

