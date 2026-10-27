# DSUUU optimize — log trace

**Author:** LATUAN · **2026.10.28** · `LATUAN_GNB_DSUUU_OPT`

How to prove a DSUUU CCE fix from logs. Companion: `gNB_cce_knowledge.md` (why two UESS seats stall DL). Do **one knob per run**. Do not mix with RF / MCS / CORESET0 hunts.

Lab: OAI gNB, n79 100 MHz, 273 PRB, 4×4, FHI 7.2, O-RU pattern-id **3** = DSUUU. Theory DL MAC / UDP ≈ **630–650 Mbit/s** (P1, MCS 26–27). Baseline UDP sat at **296 Mbit/s** with `CCE fail` climbing.

Source tree: `openairinterface5g-v26.w14`. Live DU cwd is `/var/log/oai-gnb` (`oai-du.service`), so stats files land there.

## 1. What this campaign changes

| Step | Knob | Expect in logs |
|---|---|---|
| **A** (first) | `gNBs.uess_agg_levels = [0, 4, 0, 0, 0];` | Boot: `L2: 4`. After re-attach, `CCE fail` **delta ≈ 0** on a 20 s DL offer |
| **B** | same, `[0, 6, 0, 0, 0]` | Only if A still fails. Boot: `L2: 6` |
| **C** | DL-only iperf; optional lower `min_grant_prb` / `ul_max_mcs` while measuring | Fewer UL first TX; DL takes the seats even if A is not applied |
| **Do not** | `dl_max_mcs`, CORESET0 `4→0`, TDD pattern | Those do not add UESS candidates |

Restart `oai-du` after any `gnb.conf` edit. **UE must re-attach** after A/B — UESS is in RRC.

## 2. Log map

| File | Role | Refresh |
|---|---|---|
| `/etc/oai-gnb/conf/gnb.conf` | What the DU *should* load | After edit + restart |
| `/var/log/oai-gnb/du.log` | Boot + RRC. Confirm TDD and UESS | Append |
| `/var/log/oai-gnb/nrMAC_stats.log` | Per-UE CQI/RI/MCS/NPRB/`CCE fail`/MAC bytes | **Rewrite every 1 s** |
| `/var/log/oai-gnb/nrL1_stats.log` | L1 load / PDSCH count | Rewrite ~1 s |
| iperf client | UDP DL | During the 20 s window |

`nrMAC_stats.log` is opened with `"w"` then `ftruncate` each second (`main.c`). `tail` is the current snapshot. Counters (`dlsch_rounds`, `CCE fail`, `MAC TX`) are **cumulative from attach**. Always compare **two snapshots** (t0 / t1). Do not use the absolute `CCE fail` after a long attach.

## 3. Line dictionary (`nrMAC_stats.log`)

```text
UE RNTI 987e CU-UE-ID … in-sync … average RSRP -51 …
UE 987e: CQI 15, RI 4, PMI (x,y)
UE 987e: dlsch_rounds 766226/a/b/c, dlsch_errors N, pucch0_DTX D (SNR …),
         BLER 0.04 MCS (1) 25 NPRB 273 CCE fail 498831
UE 987e: ulsch_rounds 1676576/…, … NPRB 20 … CCE fail 494895
UE 987e: MAC:    TX <bytes> RX <bytes> bytes
UE 987e: LCID 4: TX <bytes> …
```

| Token | Meaning |
|---|---|
| `dlsch_rounds` first number | Successful **first** DL TX (got a CCE + PDSCH) |
| `CCE fail` on the **dlsch** line | `dl_cce_fail` — DL DCI had no UESS seat |
| `ulsch_rounds` first number | Successful first UL TX |
| `CCE fail` on the **ulsch** line | `ul_cce_fail` |
| `MCS (1) 25` | Table 1 = 256QAM, current MCS 25 |
| `NPRB 273` | Full 100 MHz. `0` after idle — snapshot is stale |
| `MAC TX` | Cumulative DL MAC bytes (all LCIDs) |
| `LCID 4 TX` | DRB (iperf). Use this for UDP compare |

Boot line to confirm the knob (`gnb_config.c`):

```text
Candidates per PDCCH aggregation level on UESS: L1: 0, L2: 2, L4: 0, L8: 0, L16: 0
```

Default **L2: 2**. After A expect **L2: 4**. After B expect **L2: 6**.

## 4. Deltas (always)

Take two copies 20 s apart **while iperf is running**:

```text
dt        = t1 - t0                         # seconds, target 20
MAC_bps   = (TX1 - TX0) × 8 / dt            # bit/s
LCID4_bps = (LC4_1 - LC4_0) × 8 / dt
dl_ok     = dlsch0_1 - dlsch0_0             # first-TX count
dl_fail   = dlcce_1 - dlcce_0
ul_ok     = ulsch0_1 - ulsch0_0
ul_fail   = ulcce_1 - ulcce_0

dl_fail_rate = dl_fail / (dl_fail + dl_ok)   # 0 if no attempts
ul_fail_rate = ul_fail / (ul_fail + ul_ok)
```

Baseline (UE `987e`, long attach, not a 20 s window): `dl_fail_rate ≈ 0.39`, `ul_fail_rate ≈ 0.23`, UL first TX ≈ **2.2×** DL, UDP **296 / 636 ≈ 47%**.

## 5. Trace order

```text
  0  RU pattern-id 3 (DSUUU) — do not change
  1  Confirm live conf = DSUUU + current UESS
  2  Attach, air gate (CQI/RI/MCS)
  3  Baseline 20 s  (step C traffic: DL-only first)
  4  Apply A  → restart oai-du → UE re-attach
  5  Boot grep: L2 candidates
  6  After 20 s, same traffic
  7  Pass / fail → B or stop
```

### 5.1 Confirm what will load

```bash
grep -nE 'nrofDownlinkSlots|nrofUplinkSlots|dl_UL_TransmissionPeriodicity|uess_agg_levels|min_rxtxtime|min_grant_prb|ul_max_mcs|dl_max_mcs|controlResourceSetZero' \
  /etc/oai-gnb/conf/gnb.conf
```

DSUUU expect: `nrofDownlinkSlots = 1`, `nrofUplinkSlots = 3`, period idx **5** (2.5 ms), `min_rxtxtime = 2`. Before A, `uess_agg_levels` is **absent** (default L2 n2).

### 5.2 Air gate (skip CCE work if this fails)

```bash
tail -n 30 /var/log/oai-gnb/nrMAC_stats.log
```

Need **during** traffic: `CQI ≥ 10`, `RI = 4`, `Qm` 8 (`MCS (1)`), `MCS` 25–27, `NPRB 273`, `BLER ≪ 0.05`, `pucch0_DTX` not climbing, `in-sync`. If CQI 0 / RI 1 — fix RF/CSI first (not this doc).

### 5.3 Snapshot pair (copy-paste)

```bash
LOG=/var/log/oai-gnb
OUT=/tmp/dsuuu_opt
mkdir -p "$OUT"

# start iperf UDP DL (~1 Gbit/s offer), no UL iperf
sleep 2
cp "$LOG/nrMAC_stats.log" "$OUT/mac_t0.txt"
date -Is | tee "$OUT/t0.txt"
sleep 20
cp "$LOG/nrMAC_stats.log" "$OUT/mac_t1.txt"
date -Is | tee "$OUT/t1.txt"

echo '--- CSI / CCE ---'
grep -E 'CQI|dlsch_rounds|ulsch_rounds|MAC:|LCID 4' "$OUT/mac_t0.txt" "$OUT/mac_t1.txt"
```

Fill the record table in §7 from those two files.

### 5.4 Apply A and prove boot

In `gNBs { ... }` of live `gnb.conf` (only when asked to touch live):

```text
uess_agg_levels = [0, 4, 0, 0, 0];
```

```bash
sudo systemctl restart oai-du
# wait RU/FH up, then UE re-attach (airplane mode)

grep -aE 'Candidates per PDCCH aggregation level on UESS|nrofDownlinkSlots|nrofUplinkSlots' \
  /var/log/oai-gnb/du.log | tail -n 20
```

Must see `L2: 4`. If still `L2: 2` the DU did not load the new conf (wrong file, syntax, or old process).

```bash
# process + conf mtime
systemctl show oai-du -p MainPID -p ActiveEnterTimestamp --no-pager
ps -p "$(systemctl show oai-du -p MainPID --value)" -o lstart,cmd
```

### 5.5 After-A 20 s

Same commands as §5.3 into `$OUT/after_a/`. Compare fail rates and `LCID4_bps`.

## 6. Pass / fail

| Gate | Pass | Fail → |
|---|---|---|
| Boot UESS | `L2: 4` (A) or `L2: 6` (B) | Conf not loaded |
| Air | CQI/RI/MCS/NPRB as §5.2 | Stop CCE work; RF |
| `dl_fail_rate` over 20 s | **≈ 0** (a few counts OK) | Step B, or check UL first-TX still much larger than DL |
| `ul_fail_rate` over 20 s | **≈ 0** or small | More UL k2 than seats; try B or quieter UL |
| UDP DL | Toward **630–650** (DL-only) | If CCE pass but UDP low: TBS/TDA/iperf, not CCE |
| UL vs DL first TX | Can stay >1 (3 U / 1 D) | Only a problem if `CCE fail` still climbs |

Do not call A a fail because the **absolute** `CCE fail` is still huge — that is the old attach. Only the **20 s delta** counts. A new attach after restart resets the counters.

If A passes CCE but UDP stays ~300: dump `NPRB` (must be 273), `MCS`, `LCID 4` vs `MAC TX`, and iperf bind/offer. That is no longer a search-space bug.

## 7. Record sheet

Copy a row per run. One knob only.

| Field | Baseline (default L2 n2) | After A (n4) | After B (n6) |
|---|---|---|---|
| Date / time | 2026-10-28 | | |
| RNTI | | | |
| `uess_agg_levels` in conf | *(absent)* | `[0,4,0,0,0]` | `[0,6,0,0,0]` |
| `du.log` `L2:` | 2 | | |
| Traffic | DL-only UDP / bi-dir | | |
| CQI / RI / MCS / NPRB | | | |
| BLER / pucch0_DTX | | | |
| dt (s) | 20 | 20 | 20 |
| dl_ok / dl_fail | | | |
| ul_ok / ul_fail | | | |
| dl_fail_rate | ~0.39 (long run) | | |
| ul_fail_rate | ~0.23 (long run) | | |
| MAC_bps / LCID4_bps | | | |
| iperf UDP DL | 296 Mbit/s | | |
| Verdict | CCE limited | | |

## 8. Extra greps (only if a gate fails)

```bash
# UE came back after restart?
grep -aE 'Add UE|remove UE|RNTI' /var/log/oai-gnb/du.log | tail -n 30

# FH / TTI (not CCE; only if NPRB/MCS collapse)
tail -n 40 /var/log/oai-gnb/nrL1_stats.log

# scheduler order hint: UL first TX still ≳ 2× DL after A
# and CCE fail still climbs → seats still short → B
```

`du.log` has no per-slot `CCE fail` print. The counter in `nrMAC_stats.log` is the trace. `get_cce_index()` `< 0` increments `dl_cce_fail` / `ul_cce_fail` (`gNB_scheduler_dlsch.c`, `gNB_scheduler_ulsch.c`).

## 9. One line

**Trace DSUUU optimize by boot `L2: N` plus a 20 s `CCE fail` delta, not by the absolute fail count.** A is `uess_agg_levels = [0, 4, 0, 0, 0]` and a re-attach. Pass = `L2: 4`, air still CQI15/RI4, `dl_fail_rate ≈ 0`, UDP climbing toward 630–650.
