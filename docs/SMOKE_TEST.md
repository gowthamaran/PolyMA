# Real-data smoke validation — 2026-08-28 UTC

No successful strategy result was fabricated.

## What succeeded

- The live official Gamma endpoint returned 10 active market records from
  `GET https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=10&order=volume24hr&ascending=false`.
- The payload contained the fields PolyMA consumes: `id`, `conditionId`,
  `question`, `slug`, `outcomes`, `clobTokenIds`, `active`, `closed`, start/end
  dates, and market-level volume metadata.
- A current official BTC 15-minute market page was also present. This confirms
  that the target market family exists, but webpage data is not used by the
  provider and no scraping code was added.
- Official API documentation confirmed that public Data API trades contain
  `asset`, `conditionId`, `size`, `price`, and `timestamp`; these are the fields
  used to reconstruct actual 15-minute traded volume.

## What was blocked in the build workspace

The executable smoke command:

```bash
python main.py smoke-test --asset BTC --limit 1 --hours 8
```

could not resolve Polymarket DNS because the build workspace restricts direct
network egress. The provider retried four times and exited with a clear
`ProviderError`.

Therefore the honest local result is:

| Item | Result |
|---|---:|
| Live Gamma payloads inspected externally | 10 markets |
| Candles obtained by the local CLI | 0 (network blocked) |
| Local 15-minute volume validated | Not evaluated |
| Strategy signals evaluated | 0 |
| Claimed wins | 0 |

Run the same command on the Ubuntu VPS after installation. Zero signals is a
valid outcome. Do not weaken the rules to force a signal.

