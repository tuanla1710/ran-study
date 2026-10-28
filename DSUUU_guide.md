# DSUUU guide — operate, measure, resume UL

**Author:** LATUAN · **2026.10.28** · `LATUAN_GNB_DSUUU_OPT`

How to run this cell and what is still open on **UL**. Companion traces: `gNB_dsuuu_optimize_log_trace.md` (campaign log, **§10.10** open issues), `gNB_cce_knowledge.md` (CCE / UESS), `gNB_avx512_acc100_offload_design.md` (do not open UL MCS 27 until ACC100).

One knob per run. Do not mix CCE, TDD, RF, and MCS hunts.

## 1. What this cell is

OAI gNB, n79 **100 MHz**, **273 PRB**, **4×4**, FHI 7.2. O-RU pattern-id **3** = **DSUUU** = 2.5 ms, **1 D + S(10+2) + 3 U**. Not DDSUU (id 2).

| Direction | Theory (order of magnitude) | Best measured this campaign |
|---|---|---|
| **DL** | MAC/UDP ≈ **630–650** (MCS 26–27, RI 4) | MAC **627**, iperf **610** (B-class) |
| **UL** | MCS16 Qm4 RI2 ≈ **200–250**; MCS20 Qm6 ≈ **350–450** | **U0 138** @ MCS16 / 273. Latest stable **74 / server 69** @ MCS13 / 154 |

UE **UL-RI = 2** (UE cap). Do not chase UL-RI 4. DL can still be RI 4.

Worktree: `/home/oran/latuan/run/dsuuu`. Source: `openairinterface5g-v26.w14`. Live DU cwd `/var/log/oai-gnb` (`oai-du.service`).

## 2. Topology (do not confuse USB with the UE)

```text
[CPE 5G / UE]  192.168.225.1     ← power-cycle THIS box for a clean attach
        │  LAN 192.168.225.0/24
        ▼
  RTL8153 USB-LAN on PC .64
  enx2c3068009d6c = 192.168.225.127
        │
[iperf client 192.168.1.64]  oran/oranteam
        │  UDP to 10.45.0.1:5204
[gNB host]  iperf3 -s -B 10.45.0.1 -p 5204   (p5g-tp)
```

`.64` USB is **Ethernet to CPE LAN**, not the 5G modem. Cutting USB on `.64` drops `225.1`, it does **not** power-cycle the radio. Linux on `.64` sees `0bda:8153` only — no QMI/wwan.

## 3. Files that matter

| Path | Role |
|---|---|
| `/home/oran/latuan/run/dsuuu/open5g-ran-core/configs/gnb/002.gnb.sa.e2e.band79.100mhz.273.fhi72.4x4.dsuuu.conf` | **Canonical** campaign conf |
| `/etc/oai-gnb/conf/gnb.conf` | What DU loads (`MODE_IDX=3`) |
| `…/002…4x4.conf` (project, no `dsuuu`) | **Gitea original** — keep visible, do not overwrite |
| `/etc/oai-gnb/conf/002…4x4.dsuuu.conf` | **Stale** (09:51, often root). Do not use as source |
| `/etc/oai-gnb/conf/env/oai_gnb_fhi72_env.conf` | `GNB_CONF`, `MODE_IDX=3`, thread pool |
| `/var/log/oai-gnb/{nrMAC,nrL1,nrRRC}_stats.log` | Rewrite ~1 s. Deltas only |
| `/var/log/oai-gnb/du.log` | Boot UESS + RRC. Huge — do not tail as rate |

Sync rule: edit **project dsuuu** first, copy to live `gnb.conf`. After restart, boot must show UESS `L2: 6` while lab n6 is on.

### Backup / restore (manual)

```bash
cd /home/oran/latuan/run/dsuuu
backup/dsuuu-backup.sh                  # → backup/<date-time>/ + LATEST
backup/dsuuu-restore.sh --list
backup/dsuuu-restore.sh --dry-run
backup/dsuuu-restore.sh --yes --project  # live + project dsuuu
backup/dsuuu-restore.sh --yes --restart  # sudo oai-du
```

EOD 2026-10-28 snapshot: `backup/2026-10-28-eod/` (also `backup/LATEST`). Does not overwrite Gitea `…4x4.conf`. Does not copy full `du.log` or `nr_softmodem`.

## 4. Live knobs at EOD 2026-10-28

| Knob | Value | Meaning |
|---|---|---|
| TDD | DSUUU 1 / 3, 2.5 ms | Do not change |
| `uess_agg_levels` | `[0, 6, 0, 0, 0]` | Lab. Production later `[0,4,0,0,0]`. Never `[0,4,2,0,0]` (AL4 trap) |
| `ulsch_max_frame_inactivity` | **10** | Stock. `0` = PUSCH every period → I0 edge, DL 481 |
| `dl_bler` | **0.05 / 0.15** | Stock. Tight 0.03/0.05 parked IIR at 0.04, MCS 25, 527 |
| `ul_bler` | 0.05 / 0.15 | Window ~0.11 holds MCS 13 (dead zone) |
| `dl_max_mcs` | 27 | |
| `ul_max_mcs` | **20** | On disk. Air never reached MCS ≥ 17 |
| `force_UL256qam_off` | **1** | Stay 1 |
| `min_grant_prb` | 20 | Keepalive; `get_rb_alloc()` from **PRB 0** |
| ACC100 | **off** | SW LDPC. No UL MCS 27 |

`isolcpus` / `nohz_full` 2–15, 24–47 → watchdog **off** on those cores by design. Do not enable. Do not `chrt -f 99` on CPU 0–1.

## 5. DL — closed (read-only)

Limiter was **UESS seats**, not RF.

- Default L2: 2 → CCE fail, UDP **296**.
- **A** `[0,4,0,0,0]` → UDP **467**.
- **B** `[0,6,0,0,0]` → CCE ~0, PDSCH ~800/s, MCS 27, UDP **608** / MAC **628**.
- **D** `[0,4,2,0,0]` dirty = CQI 0 → `pdcch_cl_adjust` → AL4 lock → BLER 100%. Clean attach stayed AL2, UDP **487** (A-class). Do not ship AL4 n2.

Other DL traps (fixed, do not re-hunt as “CCE”):

| Symptom | Cause | Fix that worked |
|---|---|---|
| iperf 367, MAC ~606 | CPE USB **2.0** 480M | Move CPE LAN dongle to USB3 |
| iperf 481, MCS 25 | `inactivity=0` ~900 PUSCH/s × 20 PRB on PRB 0–3 | `inactivity=10` |
| iperf 527, MCS 25, BLER print 0.04000 | Tight `dl_bler` 0.03/0.05; IIR park | Stock 0.05/0.15 |

AMC is **HARQ BLER** (`get_mcs_from_bler`), not CQI. Climb needs fresh window ≤ upper **and** IIR < lower. CQI seed only if `bler ≤ upper` and `mcs+2 < cqi_mcs`.

## 6. UL — mechanisms to know before touching a knob

### 6.1 Airtime

3 U (+ 2 symbols on S), 400 periods/s → **1200 PUSCH/s** ceiling. U0 used **771**. Idle keepalive after `inactivity=10` is ~10–64/s × **20 PRB**. A real UL offer must show **NPRB 273** during iperf.

`(0)` = 64-QAM table (TS 38.214 5.1.3.1-1): MCS 0–9 QPSK, **10–16 16-QAM**, 17–28 64-QAM. `ul_max_mcs=16` **blocks 64-QAM**. `force_UL256qam_off=1` blocks table 1.

### 6.2 PUSCH vs PUCCH (open — O1)

PUCCH F2 (CSI) starts **PRB 0**, 8 PRB (4-port). PUCCH0 (HARQ) follows (~PRB 8). `get_rb_alloc()` starts **`rbStart=0`**. Keepalive 20 PRB lands on 0–19.

I0 dump (`nrL1_stats.log`): values are `n0 − avg`. Clean: avg **20**, edge not +4. After long UL: avg **32**, PRB **0–19 = +4…+5**, rest **−18**. That is PUSCH on the PUCCH edge, not an external jammer (PRACH I0 stayed ~11.6).

Printed `CQI 0, RI 1, PMI (0,0)` = **no decoded CSI**, not “channel CQI 0”. UL-RI 2 from SRS (`do_SRS=1`) can still be valid.

Raising `ulsch_max_frame_inactivity` only **thins** PUSCH. It does **not** move `rbStart`. If `vrb_map_UL` does not reserve PRB 0–7, the fix is **scheduler**, not a conf knob.

### 6.3 UL AMC (open — O3 / O4)

Same `get_mcs_from_bler` as DL (`BLER_UPDATE_FRAME 10`, `BLER_FILTER 0.9`). Live `ul_bler` 0.05/0.15. Window ~**0.11** sits in the dead zone → **hold MCS 13**. Climb needs IIR < 0.05. `ul_max_mcs=20` is untested until MCS ≥ 17 appears.

**154 PRB** at MCS 13 is the stable post-cycle rate cap (74 ≈ 138 × 154/273 × 13/16). Why 154 (TBS / BSR / split?) is unsolved.

### 6.4 SW LDPC (open — O6)

U0 MCS16 / 273 PRB / ~771 PUSCH/s **hung the host** (~10:12). ACC100 off. Until ACC100: **20 s** UL only, never 3600 s at full PRB. U1 (`ul_max_mcs=27`) and U2 (256-QAM table) stay blocked.

## 7. How to measure (5 samples, both ends)

**UDP UL** = no `-R`. **UDP DL** = `-R`. Never both in the same window.

```bash
# server (gNB host, already typical)
iperf3 -s -B 10.45.0.1 -p 5204

# client on 192.168.1.64 (src 192.168.225.127)
# UL:
iperf3 -c 10.45.0.1 -p 5204 -t 20 -i 1 -b 150M -u
# DL:
iperf3 -c 10.45.0.1 -p 5204 -t 20 -i 1 -b 650M -u -R
```

Every run: five 1 s rows of **client TX**, **server RX** (p5g-tp `/api/v1/tm/traffic/iperf-server/logs`), **MAC LCID4** (+ MCS Qm NPRB PUSCH DTX I0).

Need during UL: `NPRB 273`, `UL-RI ≥ 2`, SNR ≳ 15, UL BLER ≪ 0.05, `ulsch` CCE fail **delta** ≈ 0.  
Abort: `MCS (0) 0` + `ulsch_DTX` climbing, or host freeze.  
Idle `NPRB 20` is **not** a UL rate.

## 8. Open issues (resume order)

Full write-up: `gNB_dsuuu_optimize_log_trace.md` **§10.10**.

| # | Open | Next | Do not |
|---|---|---|---|
| **O1** | PUCCH2 CSI never decoded (CQI 0) while PUSCH OK | Does `vrb_map_UL` reserve PRB 0–7 from PUSCH? If overlap → start keepalive **above** PUCCH (code) | Call it RF CQI 0; raise inactivity as if it *moves* PRBs |
| **O2** | I0 PRB 0–19 hot (avg 32) | Idle I0 dump after rest. If still +4 @ 0–19 with no iperf → keepalive is enough | Blame `.64` USB |
| **O3** | MCS 13 / NPRB 154 / ~74 M | After CQI ≥ 13: 20 s `-b 150M`. Pass = MCS≥17 Qm6 NPRB 273 UDP>138 | `ul_max_mcs=27`; revert 16 until this row is clean |
| **O4** | UL BLER ~0.11 holds AMC | Same as DL §7.6. Loosen `ul_bler` only if O3 still stuck **after** NPRB 273 | Loosen to hide 11% HARQ |
| **O5** | U0 138 ≪ 200–250; 771 vs 1200 PUSCH/s | After O3 pass: one trial `do_SRS=0` (U4) | Mix with O1 |
| **O6** | SW LDPC host hang | ACC100 before U1=27. 20 s. isolcpus/watchdog unchanged | `chrt -f 99` on 0–1; watchdog on isolated cores |
| **O7** | Named `/etc/…dsuuu.conf` stale | `backup/dsuuu-restore.sh` → live `gnb.conf` | Use named file as truth |

**Closed:** CCE/UESS, USB2 367, DL 481 (`inactivity=0`), DL 527 (tight `dl_bler`), UL-RI 4 (U3 skip), p5g-agent (do not modify).

## 9. Do not

- Mix DL + UL iperf.
- Open `ul_max_mcs=27` or `force_UL256qam_off=0` before ACC100 **and** a passing U1-step.
- Ship `uess_agg_levels = [0, 4, 2, 0, 0]`.
- Change TDD / CORESET0 / `dl_max_mcs` for a UL hunt.
- Treat idle NPRB 20 or printed CQI 0 as a rate / RF number.
- Force-push, skip git hooks, or commit unless asked.
- Commit `open5g-ran-core` to Gitea as the campaign default; ran-study is the doc repo.

## 10. First commands tomorrow

```bash
# 1) restore if live drifted
cd /home/oran/latuan/run/dsuuu
backup/dsuuu-restore.sh --dry-run
# backup/dsuuu-restore.sh --yes --restart

# 2) air
tail -n 12 /var/log/oai-gnb/nrMAC_stats.log
# want: in-sync, CQI ≥ 13 if CSI is alive; idle NPRB 20 is OK
# I0: head of nrL1_stats.log — edge +4 and avg 32 = O1/O2 still open

# 3) do not start UL 3600 s. If CQI ≥ 13: 20 s / 150M / no -R, 5 samples.
```

Then continue at **O1**.
