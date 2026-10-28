# DSUUU optimize — log trace

**Author:** LATUAN · **2026.10.28** · `LATUAN_GNB_DSUUU_OPT`

How to prove a DSUUU CCE / UL-rate fix from logs. **Operate / resume:** `DSUUU_guide.md`. Companion: `gNB_cce_knowledge.md` (why two UESS seats stall DL). Do **one knob per run**. Do not mix with RF / MCS / CORESET0 hunts.

Lab: OAI gNB, n79 100 MHz, 273 PRB, 4×4, FHI 7.2, O-RU pattern-id **3** = DSUUU. Theory DL MAC / UDP ≈ **630–650 Mbit/s** (P1, MCS 26–27). Baseline UDP sat at **296 Mbit/s** with `CCE fail` climbing.

**DL** = §1–§9 (UESS / CCE, closed). 367 = §7.4 USB 2.0. 481 = §7.5 (`inactivity=0`). 527 = §7.6 (tight `dl_bler` 0.03/0.05). Stock `dl_bler` 0.05/0.15 + `inactivity=10` = MCS 27 / MAC 627 / iperf 610. **UL** = §10. U1-step live = `ul_max_mcs=20` but **air never used it**. Open UL issues = **§10.10**.

Source tree: `openairinterface5g-v26.w14`. Live DU cwd is `/var/log/oai-gnb` (`oai-du.service`), so stats files land there.

## 1. What this campaign changes

| Step | Knob | Expect in logs |
|---|---|---|
| **A** (first) | `gNBs.uess_agg_levels = [0, 4, 0, 0, 0];` | Boot: `L2: 4`. After re-attach, `CCE fail` **delta ≈ 0** on a 20 s DL offer |
| **B** | same, `[0, 6, 0, 0, 0]` | Only if A still fails. Boot: `L2: 6` |
| **C** | DL-only iperf; optional lower `min_grant_prb` / `ul_max_mcs` while measuring | Fewer UL first TX; DL takes the seats even if A is not applied |
| **D** | `[0, 4, 2, 0, 0]` (AL2 n4 + AL4 n2) | Boot: `L2: 4, L4: 2`. Clean UE: BLER can be 0 (stays on AL2). Dirty/CQI0: AL4 lock → BLER 100%. Do not ship as default |
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

| Field | Baseline (default L2 n2) | After A (n4) | After B (n6) | D dirty (`c2eb`) | D clean (`f9a2`) |
|---|---|---|---|---|---|
| Date / time | 2026-10-28 | **2026-10-28 09:01:35–09:02:05** | **2026-10-28 09:04:22–09:05:00** | **09:39–09:45** | **2026-10-28 09:55:53–09:56:13** |
| RNTI | `987e` | **`29ab`** | **`2003`** | **`c2eb`** | **`f9a2`** |
| `uess_agg_levels` in conf | *(absent)* | `[0,4,0,0,0]` live+project | **`[0,6,0,0,0]`** live+project | `[0,4,2,0,0]` | **`[0,4,2,0,0]`** live+project |
| `du.log` UESS | L2: 2 | **L2: 4** (08:58:11) | **L2: 6** (09:03:14) | L2: 4 L4: 2 (09:39:47) | **L2: 4 L4: 2** (09:53:06) |
| Traffic | DL UDP | DL UDP (user: unstable) | DL UDP | none (zombie) | DL UDP (LCID4) |
| CQI / RI / MCS / NPRB | 15 / 4 / 25–27 / 273 | **15 / 4 / 25 / 273** | **15 / 4 / 27 / 273** | **0 / 1 / 0 / 0** | **15 / 4 / 26 / 273** |
| BLER / pucch0_DTX | ~0 / — | **0.04** / **+1500 / 30 s** | **0** / **+0** | **1.00** / climbing + RLF | **0** / **+0** |
| dt (s) | long attach | **30** (clock, not 20) | **38** | ~3 min after restart | **20** |
| dl_ok / dl_fail | 766226 / 498831 | **20976 / 1526** | **30401 / 0** | ~260 / +~1000/s | **14000 / 2000** |
| ul_ok / ul_fail | 1676576 / 494895 | **30002 / 0** | **38000 / 0** | keepalive 20 PRB / +~850/s | **19999 / 0** |
| dl_fail_rate | ~0.39 | **0.068** | **0** | storm | **0.125** |
| ul_fail_rate | ~0.23 | **0.00** | **0** | storm | **0** |
| MAC_bps / LCID4_bps | — | **483 / 482** | **628 / 626** | ~0 / no LCID4 | **502 / 501** |
| iperf UDP DL | 296 Mbit/s | **467 Mbit/s unstable** | **608 Mbit/s** | — | **487 Mbit/s** (user, ~09:56) |
| Verdict | CCE limited | **A partial.** UL CCE gone. DL CCE 39%→7%. UDP +171. Not at 630–650. Instability = PUCCH DTX + retx 7% + MCS 25 | **B pass.** CCE gone. 800 PDSCH/s. UDP 608 ≈ 93% of MCS27 theory ~655, 97% of MAC | **D fail (dirty).** Restart without UE power-cycle. CQI0 → `pdcch_cl_adjust`→1 → AL4 n2 lock (2 seats). BLER 100% | **D clean: BLER 0.** Stays on AL2 (CQI15). UDP **487** ≈ 97% of LCID4 501. Same class as A (467). AL4 unused. Not B |

### 7.1 After-A 30 s (UE `29ab`)

```text
t0 09:01:35  dlsch 107104  dl_cce 11377  ulsch 174269  ul_cce 82
             MAC TX 9493107702   LCID4 9471248677   MCS 25 NPRB 273
t1 09:02:05  dlsch 128080  dl_cce 12903  ulsch 204271  ul_cce 82
             MAC TX 11304324096  LCID4 11278481858  MCS 25 NPRB 273

dt            = 30 s
dl_ok / fail  = 20976 / 1526     dl_fail_rate = 6.8%
ul_ok / fail  = 30002 / 0        ul_fail_rate = 0
MAC           = 1.811e9 × 8 / 30 = 483 Mbit/s
LCID4         = 1.807e9 × 8 / 30 = 482 Mbit/s
iperf UDP     = 467 Mbit/s  (~97% of LCID4)
r1 / dl_ok    = 1500 / 20976     = 7.2% HARQ retx
pucch0_DTX    = +1500             (same count as r1)
PDSCH/s       = 20976 / 30       = 699   (DSUUU ceiling 800)
```

| vs theory 636 (MCS26 P1) | After A |
|---|---|
| UDP 467 | **73%** (was 47% @ 296) |
| Seats used | UL CCE **fixed**. DL still loses ~7% |
| Why not 630 and why unstable | MCS **25** not 26; **7%** PUCCH DTX / r1; **13%** DL occasions missing (699/800); PMI (4,0)↔(4,1). TTI skip after restart: **2** only |

### 7.2 After-B 38 s (UE `2003`)

```text
t0 09:04:22  dlsch 27061   dl_cce 32   ulsch 33751   ul_cce 70
             MAC TX 2644915993   LCID4 2639107990   MCS 27 NPRB 273
t1 09:05:00  dlsch 57462   dl_cce 32   ulsch 71751   ul_cce 70
             MAC TX 5626304087   LCID4 5613951757   MCS 27

dt            = 38 s
dl_ok / fail  = 30401 / 0        dl_fail_rate = 0
ul_ok / fail  = 38000 / 0        ul_fail_rate = 0
MAC           = 2.981e9 × 8 / 38 = 628 Mbit/s
LCID4         = 2.975e9 × 8 / 38 = 626 Mbit/s
iperf UDP     = 608 Mbit/s  (~97% of LCID4, ~93% of 655 MCS27 theory)
PDSCH/s       = 30401 / 38       = 800   (DSUUU ceiling)
pucch0_DTX    = +0
r1            = +1
```

B clears the leftover 7% DL CCE. AMC can sit on MCS 27 / BLER 0. Remaining ~20–45 Mbit/s to 650 is TBS/iperf, not search space.

### 7.3 Step D — `[0, 4, 2, 0, 0]` (AL2 n4 + AL4 n2)

OAI `get_cce_index()` picks the **first** AL with candidates (`determine_aggregation_level_search_order`). PUCCH/PUSCH miss raises `pdcch_cl_adjust` (+0.05). At ≥ ~0.375 it starts at AL4. If `L4: 2`, it **does not fall back** to the four AL2 seats.

#### 7.3a Dirty attach (UE `c2eb`, 09:39–09:45) — FAIL

DU restart 09:39:47 onto production-trial `[0,4,2,0,0]` while the previous UE was still up. Same RNTI `c2eb` came back via C-RNTI / broken RA (Msg4 NACK, Release, RLF). No new RRC SearchSpace.

```text
CQI 0, RI 1, MCS 0, NPRB 0, LCID4 absent
BLER DL/UL = 1.00   pucch0_DTX climbing   RLF
CCE fail   ≈ +1000/s DL, +850/s UL
```

Verdict: **not RF**. CQI0 locked MAC on AL4 n2 (2 seats) for a DSUUU slot that wants 3 UL + 1 DL.

#### 7.3b Clean UE (UE `f9a2`, 09:55:53–09:56:13) — BLER 0, CCE not gone

User power-cycled the UE. DU boot 09:53:06: `L2: 4, L4: 2`. New RNTI `f9a2`, S-TMSI `c0000191`, RSRP **−51**, PDU session up.

```text
t0 09:55:53  dlsch 41990  dl_cce 5822  ulsch 104301  ul_cce 9700
             MAC TX 3605246292   LCID4 3595409163   MCS 26 NPRB 273
             CQI 15 RI 4  BLER 0  pucch0_DTX 0
t1 09:56:13  dlsch 55990  dl_cce 7822  ulsch 124300  ul_cce 9700
             MAC TX 4861170292   LCID4 4848572846   MCS 26 NPRB 273

dt            = 20 s
dl_ok / fail  = 14000 / 2000     dl_fail_rate = 12.5%
ul_ok / fail  = 19999 / 0        ul_fail_rate = 0
MAC           = 1.256e9 × 8 / 20 = 502 Mbit/s
LCID4         = 1.253e9 × 8 / 20 = 501 Mbit/s
iperf UDP     = 487 Mbit/s  (~97% of LCID4; user report 09:56)
PDSCH/s       = 14000 / 20       = 700   (DSUUU ceiling 800)
pucch0_DTX    = +0
r1            = +0
L1            = Qm 8, RI 4
```

| vs A (n4 only) | vs B (n6) | This clean D |
|---|---|---|
| MCS 25, MAC 483, UDP 467, DL CCE 6.8%, PDSCH 699/s | MCS 27, MAC 628, UDP 608, CCE 0, PDSCH 800/s | MCS **26**, MAC **502**, UDP **487**, DL CCE **12.5%**, PDSCH **700/s** |

**What D clean proves:** with CQI 15, `pdcch_cl_adjust` stays ~0 so MAC uses **AL2 n4**. AL4 n2 is idle. BLER **0** (user: “DL hết bị BLER”). UDP **487** ≈ A (467), not B (608). The extra `2` does **not** add seats while the channel is good.

**What D dirty still proves:** the same conf + a half-dead attach (CQI 0) **does** lock AL4 and print BLER 100%. Reset UE before judging this knob.

Do not call D a production default. Keep production **`[0, 4, 0, 0, 0]`** (A, no AL4 lock). Lab 1-UE peak remains **`[0, 6, 0, 0, 0]`** (B).

### 7.4 Post-reboot “367 Mbps” (2026-10-28 10:36–10:51) — not CCE

Host hard-lock ~10:12 during U0 UL (MCS16, 273 PRB, SW LDPC, ACC100 off). Manual reboot 10:21. DU up 10:30, restart 10:36:00 onto live `ul_max_mcs=20`, UESS **`[0, 6, 0, 0, 0]`**. New UE `ea59` (S-TMSI `c0000324`). User: iperf DL only 367 after reboot.

**Not** D-dirty: CQI 15, RI climbs 2→4 in ~20 s, MCS 27, NPRB 273, `dlsch_errors 0`, DL CCE delta **0**. Early 367 window overlapped **RI 2**. After RI 4, air is B-class again.

Agent retest **10:47–10:48** (stopped the 3600 s `-b 1000M` run first):

```text
client  192.168.1.64  /  UE LAN 192.168.225.127  enx2c3068009d6c
cmd     iperf3 -c 10.45.0.1 -p 5204 -t 20 -i 1 -b 650M -u -R
server  this host: iperf3 -s -B 10.45.0.1 -p 5204   (p5g-tp)

t0/t1 ~20.98 s   UE ea59   CQI 15  RI 4  MCS 27  BLER 0.015  CCE +0
ogstun TX        577 Mbit/s
MAC / LCID4 TX   607 / 606 Mbit/s
PDSCH/s          776   (ceiling 800)   retx 7.1/s   pucch0_DTX +0
iperf sender     650 Mbit/s
iperf receiver   367 Mbit/s  every 1 s flat   Lost 428168/1108859 (39%)
client NIC RX    379 Mbit/s  drop 0
```

| Layer | Mbps | Meaning |
|---|---|---|
| ogstun TX | 577–1021 | `-b 650M` / earlier `-b 1000M` into N6 |
| MAC LCID4 | **606–621** | B-class air (was 628 @ 09:04). gNB OK |
| Client `enx2c3068009d6c` | **379** | USB Ethernet into CPE LAN |
| iperf UDP RX | **367** | = NIC, not MAC |

`enx2c3068009d6c` = RTL8153 on **USB 2.0 480M** (`usb1/1-2`, `USB_VER 2.10`). ethtool 1000/full, bus 480 → practical ceiling **~367**. Same host already has a second RTL8153 on **USB 3 5000M** (`Bus 002`). Move the CPE cable there; do not touch UESS / MCS / TDD for this number.

`-b 1000M` on a 620 Mbit/s DSUUU pipe also dumps ~400 Mbit/s before MAC. That does **not** create the flat 367 — USB 2.0 does.

After the CPE moved to USB 3 (`usb2/2-2`, 5000M), iperf tracked MAC again (531 ≈ 540, then 386 / 481). That is §7.5, not USB.

### 7.5 Plateau 481 / MCS 25 (2026-10-28 11:10–11:37) — UL keepalive, not CCE

USB 3 OK. UESS still **`[0, 6, 0, 0, 0]`**. Not AL4, not “nhiễu ngoài” on DL (CQI stayed 15).

`ulsch_max_frame_inactivity = 0` pre-grants PUSCH **every frame** (`min_grant_prb=20`) even on UDP DL. Measured on UE `2974` while iperf `-b 650M -u -R` 3600 s:

```text
PUSCH/s ~900   NPRB 20   ulsch_power ~48–63   (clean was ~39)
avg_I0  24–35  (clean 20)    max_IO 35–51 @ PRB 0–3 or 8
PRACH I0 15–25 (clean 12)
pucch0_DTX +50/s    HARQ r1 100/749 = 14.3%    printed BLER 0.04 (IIR)
MCS 25 locked    PDSCH 700/s    MAC 494    iperf 481
```

PUCCH sits on the **low BWP edge**. Hot PRB 0–3 → missed ACK (DTX) even when decoded PUCCH SNR ~24 dB. AMC: climb needs fresh window ≤ 5% (`get_mcs_from_bler`). 14% → **no** MCS 26–27. CQI seed needs `mcs+2 < cqi_mcs`; 25+2 ≮ 27. Formula: `608 × 700/800 × 25/27 ≈ 493`.

Stopping iperf did **not** drop I0 — keepalive still ran. `unknown TEID 0xd36da383` after re-attach = UPF still blasting the **deleted** tunnel of `ea59` (one log line per GTP-U packet; 679k lines). Not RF.

**Knob (one):** `ulsch_max_frame_inactivity` **0 → 10** (OAI stock). Project + live `gnb.conf` synced 11:32. Named `/etc/…4x4.dsuuu.conf` still stale (root). DU restart **11:36:07**, boot `L2: 6`. Ping may ~30 ms; revert 0 if RTT must stay low. Do not touch UESS / TDD / `min_grant_prb` / `ul_max_mcs` 27.

**After** (UE `793f`, S-TMSI `c00004da`, 11:37, 5 s):

```text
CQI 15  RI 4  MCS 27  BLER 0.0045  NPRB 273  CCE +0  pucch0_DTX +0
MAC / LCID4  623 / 621   PDSCH 794/s   retx 3/s
PUSCH/s 64   (was ~900)   UL MCS 20 Qm 6 NPRB 20
avg_I0 20 (14.14.12.14)   max_IO 18 @ 86   PRACH 11.6
ulsch_power ~39   noise ~12
```

Same class as B (MAC 628 / UDP 608). I0 map back to the 10:42 clean snapshot. Cause **confirmed**: inactivity=0 keepalive, not external jammer, not CCE.

| | 367 USB2 | 481 plateau | **11:37 after =10** | B 09:04 |
|---|---|---|---|---|
| USB | 480M | 5000M | 5000M | — |
| inactivity | 0 | **0** | **10** | 0 (short window) |
| MCS / PDSCH/s / DTX | 27 / 776 / 0 | 25 / 700 / 50 | **27 / 794 / 0** | 27 / 800 / 0 |
| MAC / iperf | 606 / 367 | 494 / 481 | **623 / (user: lên lại)** | 628 / 608 |

### 7.6 Plateau 527 / MCS 25 then stock `dl_bler` (2026-10-28 11:41–11:45)

After §7.5 (`inactivity=10`) air was B-class (MCS 27, MAC 623, retx 3/s). ~11:41 it dropped without config change:

```text
MCS 25  BLER print 0.04000 (IIR park)  LCID4/MAC 540/541  PDSCH 750/s
retx 50/s = 6.7%   DTX 0   I0 20   CQI 15   CCE +0   PUSCH 63/s
iperf ~527
```

Not inactivity, not I0, not USB. AMC: `dl_bler_target` **0.03/0.05**. One 100 ms first-HARQ window > 5% → MCS 27→25. Floor-recovery sets IIR = (0.03+0.05)/2 = **0.04000**. Climb needs IIR < 0.03 **and** fresh window ≤ 5%. Fresh window stayed 6.7% → dead zone. CQI 15 does not pull MCS.

**Knob (one):** `dl_bler_target_lower/upper` **0.03/0.05 → 0.05/0.15** (OAI stock). Project + live synced 11:43. Tight pair left `#if 0`. DU restart **11:44:15**, boot `L2: 6`. UL bler unchanged 0.05/0.15. Revert tight if MCS 27 HARQ > 15%.

**After** (UE `1310`, 11:45, 12 s, iperf user **610**):

```text
CQI 15  RI 4  PMI (6,0)  MCS 27  BLER 0.0000–0.0008  NPRB 273  CCE +0
MAC / LCID4  627 / 625   PDSCH 799/s   retx 0.3/s   DTX 0
PUSCH/s 100   UL MCS 20
avg_I0 29   max_IO 47–48 @ PRB 8   (warmer than 11:37 clean 20; DL not limited)
```

Same class as B. Stock outer loop holds MCS 27 with a 6%-class window; tight 0.03/0.05 does not.

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

## 10. UL campaign

DL CCE work is done. UL on this cell is **not** seat-limited: A / B / D-clean all had `ul_fail_rate = 0`. The cap is MCS table + `ul_max_mcs`. One knob per run. Do **not** retouch UESS / TDD / CORESET0 here.

### 10.1 Why UL is short — U0 measured (2026-10-28 10:10:18–10:10:38, UE `f41f`)

```text
UL-RI 2   SNR 23 dB   BLER 0.07   MCS (0) 16   Qm 4   NPRB 273
ul_max_mcs = 16          force_UL256qam_off = 1
ul_cce_fail delta = 0    PUSCH/s = 771   (ceiling 3×400 = 1200)
MAC RX 138 Mbit/s        LCID4 RX 138 Mbit/s
```

| Hold (do not change unless a listed UL step) | Live 10:10 |
|---|---|
| TDD | DSUUU 1 / 3, 2.5 ms |
| `min_rxtxtime` / `min_grant_prb` | 2 / 20 |
| `pusch_AntennaPorts` | 4 |
| UESS | `[0, 6, 0, 0, 0]` (DU 10:07:41) |

`(0)` = 64-QAM table (TS 38.214 5.1.3.1-1). On that table MCS **0–9** QPSK, **10–16** 16-QAM, **17–28** 64-QAM. So `ul_max_mcs = 16` **blocks 64-QAM**. `force_UL256qam_off = 1` blocks the 256-QAM table. SNR ~24 dB is enough to try both. Idle `NPRB 20` is keepalive (`min_grant_prb`); a real UL offer must show **NPRB 273**.

DSUUU UL airtime: **3 U + 2 symbols on S**, 400 periods/s.

```text
UL_bps = (MAC_RX1 − MAC_RX0) × 8 / dt
       ≈ (LCID4_RX1 − LCID4_RX0) × 8 / dt     # UDP compare
```

Order-of-magnitude (273 PRB, 3 U, ignore S): MCS16 Qm4 **UL-RI2 ~200–250**; 64-QAM MCS20+ UL-RI2 ~350–450. **UE UL cap = RI 2** (user 2026-10-28) — do not chase UL-RI4. DL RI4 still valid (try B). `pusch_AntennaPorts=4` is unused UL headroom. Fill the measured row — do not treat this as TBS.

### 10.2 Steps

| Step | Knob | Expect |
|---|---|---|
| **U0** | none — UDP UL on live cap | **Done 10:10.** NPRB 273, MCS 16, Qm 4, UL-RI 2, LCID4 **138**. CCE 0. Host hung ~10:12 (SW LDPC, no ACC100) |
| **U1-step** | `ul_max_mcs` **16 → 20** (not 27) | Conf 10:30. Dirty FAIL 11:51/11:53. After CPE power-cycle **12:02: stable 74 @ MCS13 / 154**, not ≥17/Qm6/273. **Open §10.10.** Not U1=27 |
| **U1** | only if U1-step holds + ACC100 on: **20 → 27** | MCS toward 27, Qm 6. Abort if host load / DTX |
| **U2** | only if U1 holds: `force_UL256qam_off` **1 → 0** | `MCS (1)`, Qm 8. Risk: MCS(1)+MCS0 DTX (2026-07-15). Abort to U1 |
| **U3** | ~~UL-RI 2→4~~ | **Skip.** UE **UL** cap is RI=2 (user 2026-10-28). DL can still be RI4 (B: CQI15 / RI4). Not a gNB UL knob |
| **U4** | only if PUSCH/s still ~770 after U1: `do_SRS` 1→0 one trial | SRS may eat a U slot (771 vs 1200). Abort if TA/TPMI break |
| **Do not** | TDD, CORESET0, `dl_max_mcs`, `min_grant_prb`, mix DL+UL iperf | Bidirectional is a separate row |

Restart `oai-du` after U1/U2. Re-attach UE (`ul_max_mcs` is MAC; 256-QAM table is RRC).

### 10.3 Air gate (skip the next knob if this fails)

```bash
tail -n 12 /var/log/oai-gnb/nrMAC_stats.log
```

Need **during** UDP UL: `NPRB 273`, `UL-RI ≥ 2`, `SNR ≳ 15`, `BLER ≪ 0.05`, `ulsch` `CCE fail` delta ≈ 0, `LCID 4 RX` climbing. If `NPRB` stays 20 — no BSR / no iperf, not an MCS problem. If `MCS (0) 0` + `ulsch_DTX` climbing — abort, back to previous cap.

### 10.4 Snapshot pair (UL)

Same 20 s idea as §5.3. Traffic = **UDP UL only** (UE → gNB). No DL iperf in the same window.

```bash
LOG=/var/log/oai-gnb
OUT=/tmp/dsuuu_opt/ul
mkdir -p "$OUT"

# start iperf UDP UL (~1 Gbit/s offer), no DL iperf
sleep 2
cp "$LOG/nrMAC_stats.log" "$OUT/mac_t0.txt"
date -Is | tee "$OUT/t0.txt"
sleep 20
cp "$LOG/nrMAC_stats.log" "$OUT/mac_t1.txt"
date -Is | tee "$OUT/t1.txt"

echo '--- UL ---'
grep -E 'UL-RI|ulsch_rounds|MAC:|LCID 4' "$OUT/mac_t0.txt" "$OUT/mac_t1.txt"
```

```text
dt         = t1 − t0
UL_MAC     = (MAC_RX1 − MAC_RX0) × 8 / dt
UL_LCID4   = (LC4_RX1 − LC4_RX0) × 8 / dt
ul_ok      = ulsch0_1 − ulsch0_0
ul_fail    = ulcce_1 − ulcce_0
PUSCH/s    = ul_ok / dt          # DSUUU ceiling 3 U × 400 = 1200 (+ S)
```

Also copy DL `pucch0_DTX` / `BLER` / `MCS` in the same window — U1/U2 fail if they poison DL.

### 10.5 Record sheet

| Field | U0 (live cap) | U1-step (`ul_max_mcs=20`) | U1 (`=27`) | U2 (UL 256-QAM) |
|---|---|---|---|---|
| Date / time | **2026-10-28 10:10:18–10:10:38** | **12:02 after UE power-cycle — stable, not U1** | | |
| RNTI | **`f41f`** | live UE **`ea59`** (after reboot) | | |
| `ul_max_mcs` | **16** | **20** (live+project) | 27 | 27 |
| `force_UL256qam_off` | **1** | **1** | 1 | **0** |
| UL-RI / SNR / MCS / Qm / NPRB | **2 / 23 / 16 / 4 / 273** | **2 / 23.7 / 13 / 4 / 154** (5 mẫu phẳng) | | |
| UL BLER / ulsch_DTX | **0.07 / +0** | | | |
| ul_fail_rate | **0** | attach leftover 9584, **delta 0** after settle | | |
| PUSCH/s | **771** (ceil 1200) | idle keepalive ~924 @ NPRB 20 | | |
| UL MAC / LCID4 RX | **138 / 138** | **74 / 74** (5 mẫu phẳng) | | |
| iperf UDP UL | *(≈ LCID4 138)* | client TX **155** / server **~69** (54% loss) | | |
| DL side-effect (DTX / BLER / MCS) | DTX +0 / 0.04 / 25, NPRB 0 | DL air **606** @ MCS27 / CCE 0 (§7.4) | | |
| Verdict | **U0 baseline.** Cap = MCS 16. Hang ~10:12 = SW LDPC + isolcpus, not MCS27 | **Stable but not U1-step.** MCS 13 Qm4 NPRB 154. Server 69 < U0 138. CQI 0. Do not open 27 | | |

U0 is **empty until the first UDP UL run**. Do not use the idle `NPRB 20` snapshot as a UL rate.

### 10.6 Pass / fail

| Gate | Pass | Fail → |
|---|---|---|
| Offer | `NPRB 273`, `LCID 4 RX` rising | Start iperf UL; check UE route / PDU |
| U0 | MCS 16, Qm 4, BLER ≪ 0.05, number on the sheet | RF / attach first |
| U1-step | MCS ≥ 17, Qm 6, UL UDP > 138, DL DTX not climbing, host stays up | back to 16 |
| U1 (27) | only after ACC100 + U1-step pass | back to 20 |
| U2 | `MCS (1)`, UL UDP > U1, no DTX storm | `force_UL256qam_off=1` |
| CCE | `ul_fail_rate` still ≈ 0 | stop UL MCS work; seats are gone — that is §1 again |

### 10.7 Host hang + U1-step apply (2026-10-28)

| When | What |
|---|---|
| ~10:12 | Host lock during U0 UL iperf (MCS16, NPRB 273, ~771 PUSCH/s, software LDPC). Journal cut mid-PTP. `isolcpus`/`nohz_full` 2–15,24–47 → watchdog **off** on those cores by design. Not a login bug. Do **not** enable watchdog on isolated cores. Do **not** `chrt -f 99` on CPU 0–1 |
| 10:21 | Manual reboot |
| 10:30 | Live `ul_max_mcs` **16→20**. UESS kept **`[0, 6, 0, 0, 0]`**. `force_UL256qam_off=1`. ACC100 / `pf-bb-config` still **inactive** |
| 10:36:00 | DU restart (PID 139675, `-O /etc/oai-gnb/conf/gnb.conf`) |
| 10:47 | §7.4 DL retest. U1 UL iperf **not** started |
| 11:10–11:31 | §7.5: USB3, iperf 531→386→**481** stuck MCS 25. `inactivity=0` → ~900 PUSCH/s, I0 edge, PUCCH DTX 50/s |
| 11:32 | Project + live: UESS n6, `ulsch_max_frame_inactivity` **10**. Named `/etc/…dsuuu.conf` not writable |
| 11:36:07 | DU restart. UE `793f`. MAC **623**, MCS 27, DTX 0, PUSCH **64/s**, I0 20 |
| 11:41 | §7.6: MCS 25, BLER print 0.04, retx 50/s, MAC 541 / iperf 527. Tight `dl_bler` 0.03/0.05 dead zone |
| 11:43 | Project + live: `dl_bler` **0.05/0.15** stock |
| 11:44:15 | DU restart. UE `1310`. MAC **627**, LCID4 625, MCS 27, retx 0.3/s, iperf **610** |
| 11:48 | §10.8: leftover 3600 s `-b 150M` killed; UE dirty |
| 11:51:05–27 | Agent UL 20 s `-b 150M`. Client 150 flat. Server **23.5** / 84% loss. MAC 1.8–53, MCS 0–13, NPRB≠273. **FAIL U1-step** |
| 11:53 | Idle `4742` looked OK (UL MCS 14 DTX 0 CQI 15). Retry 20 s same knob. MAC 1.1–57, MCS 2–14, NPRB ≤171, DTX 0–401, UE bounce. iperf client hung >20 s — killed. New UE `fe5a` CQI 0. **FAIL again** |
| 12:10 | **EOD.** Backup `dsuuu/backup/2026-10-28-eod/` (+ `backup/LATEST`). Live=`project` dsuuu.conf. Resume: RESTORE.md — CQI/PUCCH edge, not MCS 27 |
| 12:29 | §10.10 open UL issues O1–O7 written. Scripts `backup/dsuuu-backup.sh` / `dsuuu-restore.sh` |

Safe UL path stays: keep isolcpus/watchdog as-is → ACC100 before MCS 27 → fill U1-step UDP UL (20 s) vs U0 138. Abort on DTX storm or host load.

### 10.9 CQI 0 after power-cycle (2026-10-28 12:05) — PUCCH edge, not “kênh CQI 0”

UE `7a45` in-sync, RSRP −50, PUSCH SNR 22–24, `ulsch_DTX` 0. Printed `CQI 0, RI 1, PMI (0,0)` = **default / no decoded CSI**, not a measured CQI. UL-RI 2 from SRS (`do_SRS=1`) works.

```text
I0: PRB 0–19 = +4…+5   rest = −18…−21
avg_I0 32 (clean 20)   max_IO 37 @ PRB 2   PRACH I0 11.6
PUCCH F2 startPRB 0, nPRB 8 (4-port)   PUCCH0 after that (~PRB 8)
min_grant_prb 20   get_rb_alloc() starts rbStart=0
pucch0_DTX still +1/s idle   DL MCS 0 BLER 0.48–0.55
```

Same class as §7.5 (PUCCH on low edge + PUSCH keepalive). `inactivity=10` reduced rate to ~10 PUSCH/s but 20 PRB still land on 0–19. After 3600 s UL the edge stayed hot. CSI on PUCCH2 never lands → CQI stays 0 → seed gated (`dl_bler` 0.48 > upper 0.15) → DL MCS 0 spiral. UL AMC independent → MCS 13 / 154 / 74 M.

Do **not** open `ul_max_mcs=27`. One-knob candidates (only if asked): raise `ulsch_max_frame_inactivity` (rest PUSCH more) **or** wait I0→20 then new CSI; do not retouch UESS/TDD.

### 10.10 Open issues — UL concepts / ops / mechanisms to study

Resume here. DL CCE is closed. `ul_max_mcs=20` is **on disk only**. Do not open 27 / UL 256-QAM / UESS / TDD until the rows below are answered. One knob per run. Measure 5×1 s client + server + MAC.

**Where we stopped (12:02–12:07, UE `7a45`):**

| | U0 10:10 (`f41f`) | After power-cycle 12:02 (`7a45`) | Want for U1-step |
|---|---|---|---|
| MCS / Qm / NPRB | 16 / 4 / **273** | **13 / 4 / 154** | ≥17 / **6** / **273** |
| MAC / iperf server | 138 / ~138 | **74 / ~69** (client TX 155, 54% loss) | **> 138** |
| UL BLER / DTX | 0.07 / 0 | **0.11 / 0** | ≪ 0.05 / 0 |
| CQI / DL | (not limiter) | **CQI 0**, DL MCS 0, `pucch0_DTX` +1/s | CQI ≥ 13, DL DTX calm |
| I0 | — | avg **32**, PRB **0–19 +4** (clean 20) | avg ~20, edge not hot |

Theory DSUUU UL (3 U, UL-RI 2, ignore S): MCS16 Qm4 ~200–250; MCS20 Qm6 ~350–450. U0 138 already short of that. 12:02 is half of U0 (154/273 × 13/16 ≈ 74).

#### Issues (what broke)

| ID | Issue | Evidence | Not this |
|---|---|---|---|
| **UL-I0** | Keepalive PUSCH sits on PUCCH | `min_grant_prb=20` + `get_rb_alloc()` `rbStart=0`. PUCCH F2 PRB 0–7, F0 ~8. I0 0–19 hot after 3600 s UL and still idle | External jammer (PRACH I0 11.6, rest of BWP −18) |
| **UL-CSI** | Printed CQI 0 = **no decoded CSI** | Default `CQI 0, RI 1, PMI (0,0)`. UL-RI 2 from SRS works. PUCCH2 never lands | “Channel is CQI 0” |
| **UL-AMC** | UL outer loop **holds MCS 13** | `ul_bler` 0.05/0.15; window ~0.11 ∈ dead zone. Same `get_mcs_from_bler` as DL §7.6 | `ul_max_mcs=20` (never reached) |
| **UL-PRB** | Offer never **273** after U0 | Stable **154** @ MCS 13. Idle 20 = keepalive (not a rate) | Missing iperf (client TX 155) |
| **UL-LDPC** | SW LDPC hangs host at full UL | U0 MCS16 / 273 / ~771 PUSCH/s → lock 10:12. isolcpus 2–15,24–47, watchdog off by design | MCS 27 (not applied) |
| **UL-ATT** | Dirty attach / UE bounce | 11:51–11:53 RNTI churn, MCS 0, DTX 400/s. Power-cycle fixed **stability**, not CQI/154 | USB on `.64` (LAN only; CPE is `225.1`) |
| **UL-GAP** | U0 138 ≪ theory 200–250 | PUSCH/s **771** vs ceil **1200**. Possible SRS (`do_SRS=1`) eating a U slot — **U4**, do not run yet | CCE (`ul_fail_rate` delta 0) |

#### Concepts / operations / mechanisms to study (before the next knob)

1. **PUSCH–PUCCH coexistence on DSUUU 3 U**  
   `nr_radio_config.c`: F2 `startingPRB=0`, `nrofPRBs=8` (4-port). `gNB_scheduler_ulsch.c`: inactivity grant uses `get_rb_alloc(min_grant_prb, …)` from PRB 0 (`gNB_scheduler_primitives.c`). **Study:** is PUCCH in `vrb_map_UL` when PUSCH is allocated? If not, 20 PRB keepalive **is** the CSI killer. Moving `rbStart` (code) ≠ raising inactivity (still lands on 0).

2. **`ulsch_max_frame_inactivity` vs I0**  
   `nr_UE_is_to_be_scheduled()`: `0` → at least every TDD period (~900 PUSCH/s × 20 PRB → §7.5 DL 481). `10` → ~100 ms rest (~10–64 PUSCH/s). **Study:** does 10→50 only *thin* the heat, or can I0 return to 20 while CSI still fails because each grant is still PRB 0–19? Ping/RTT cost.

3. **CSI path (PUCCH2 vs PUSCH UCI)**  
   `gNB_scheduler_uci.c` `extract_pucch_csi_report` / `evaluate_cqi_report`. Seed gated if `dl_bler > upper` (0.15) — even a late CQI 15 will **not** raise DL MCS while BLER 0.48. **Study:** does any CSI ride on PUSCH UCI during UL iperf? Why first CSI after attach never decodes when I0 edge is hot.

4. **UL AMC + PRB sizing**  
   Same IIR (`BLER_FILTER 0.9`, 10-frame window) as DL. Climb needs avg **< lower (0.05)** and window ≤ upper. **Study:** why **154** PRB (fixed split? TBS for 150 M offer? BSR underestimate?) vs U0 **273**. Until NPRB=273 and MCS≥17, `ul_max_mcs=20` is untested.

5. **DSUUU UL budget**  
   3 U + 2 S symbols, 400 periods/s → 1200 PUSCH/s. U0 used 771. **Study:** SRS (`do_SRS`) vs unused U slot (U4). UE **UL-RI=2** is a UE cap — do not chase RI 4 on UL. `pusch_AntennaPorts=4` is unused headroom.

6. **SW LDPC / ACC100**  
   Full-PRB UL = host-level risk (`gNB_avx512_acc100_offload_design.md`). **Study:** safe PUSCH/s or NPRB cap without ACC100; 20 s only; never 3600 s at 273 PRB. U1 (`=27`) and U2 (256-QAM table) stay blocked.

7. **Measure ops (do not mix)**  
   Topology: CPE `192.168.225.1`, client `.64` = USB-LAN only. UDP UL = no `-R`. 5 samples: client TX, p5g-tp server RX, MAC LCID4 RX. Abort: MCS 0 + `ulsch_DTX` climb, or host freeze. Do not mix DL+UL iperf.

#### Open issue list (resume order)

| # | Open | Next action | Do not |
|---|---|---|---|
| **O1** | PUCCH2 CSI never decoded (CQI 0) while PUSCH OK | Confirm whether `vrb_map_UL` reserves PRB 0–7 from PUSCH. If overlap: **code** (start keepalive above PUCCH), not a conf knob. Optional wait I0→20 | Call it “RF CQI 0”; do not raise inactivity as if it *moves* PRBs |
| **O2** | I0 PRB 0–19 hot (avg 32) after UL / keepalive | Re-dump `nrL1_stats` I0 **idle** after a night. If still +4 @ 0–19 with no iperf → keepalive is enough | Blame `.64` USB power |
| **O3** | MCS 13 / NPRB 154 / ~74 M (U1-step fail, but stable) | After **O1** (CQI≥13): 20 s `-b 150M`. Pass = MCS≥17 Qm6 NPRB 273 UDP>138 | `ul_max_mcs=27`; revert 16 until this row is run clean |
| **O4** | UL BLER ~0.11 holds AMC in [0.05, 0.15] | Same study as DL §7.6. Only loosen `ul_bler` if O3 still stuck **after** NPRB 273 | Loosen to hide 11% HARQ |
| **O5** | U0 138 vs theory 200–250; PUSCH 771 vs 1200 | After O3 pass: one trial `do_SRS` 0 (U4). Abort if TA/TPMI break | Mix with O1 |
| **O6** | SW LDPC host hang | ACC100 on before U1=27. Until then: 20 s, watch host. isolcpus/watchdog unchanged | `chrt -f 99` on CPU 0–1; enable watchdog on isolated cores |
| **O7** | Named `/etc/…4x4.dsuuu.conf` stale 09:51 | Restore via `backup/dsuuu-restore.sh` → live `gnb.conf` only | Use named file as source of truth |

**Closed (do not re-open as UL):** CCE/UESS (§1–§9). USB2 367 (§7.4). DL 481 = `inactivity=0` (§7.5). DL 527 = tight `dl_bler` (§7.6). UL-RI 4 (U3 skip). p5g-agent.

## 9. One line

**DL:** trace by boot `L2: N` plus a `CCE fail` delta, not the absolute count. A (`n4`) cut fail 39%→7% and UDP 296→467. B (`n6`) zeroed CCE, 800 PDSCH/s, MCS 27, UDP **608** / MAC **628**. D dirty = BLER 100% (AL4 lock); D clean `f9a2` = UDP **487** (A-class). Production **`[0,4,0,0,0]`**. 367 after reboot = **USB 2.0** (MAC 606). 481 stuck MCS 25 = **`ulsch_max_frame_inactivity=0`**. 527 stuck MCS 25 = tight **`dl_bler` 0.03/0.05** (IIR park 0.04; retx 6.7%). Live now: `inactivity=10` + stock `dl_bler` 0.05/0.15. UE `1310` MAC **627**, LCID4 625, MCS 27, retx 0.3/s, iperf **610** (B-class). Not CCE.

**UL:** CCE is no longer the limiter. U0 = MCS16 / LCID4 **138**. After UE power-cycle: stable **74 / server 69** @ MCS 13 Qm4 NPRB 154. CQI **0** = no CSI (PUCCH2 on PRB 0–7). I0 PRB 0–19 hot. **Open §10.10** O1–O7 (PUCCH/PUSCH overlap, AMC 13/154, SW LDPC). Not MCS 27.
