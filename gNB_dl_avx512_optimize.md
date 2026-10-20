# gNB downlink optimize tracking

Living log for **DL throughput / air-interface work** on the n79 100 MHz O-DU (FHI 7.2, 4×4).  
Companion to [du_max_throughput_tracking.md](du_max_throughput_tracking.md) (full run history). This file is the **optimize plan + new measurements only**.

**Rule:** one knob (or one binary change) per row. Do not start E2E DL optimize until the TM3.1a original baseline row is filled.

---

## 0. Tag rule — `PORTING_AVX512_DL_OPTIMIZE`

Every modification or add for **this DL optimize campaign** is stamped so it can be grepped and reverted independently of the CPU port and older E2E/TM work.

**One name only** — CMake option, compile macro, and comment stamp are all `PORTING_AVX512_DL_OPTIMIZE`. Do **not** add a second `__PORTING_AVX512_DL_OPTIMIZE__` define.

**Canonical stamp**

```text
PORTING_AVX512_DL_OPTIMIZE /* HAVE LATUAN YYYY.MM.DD */
```

| Field | Value |
|---|---|
| Tag / macro | `PORTING_AVX512_DL_OPTIMIZE` |
| Author | `LATUAN` |
| Date | `YYYY.MM.DD` (day of the edit, e.g. `2026.10.19`) |
| Find all | `grep -RIn PORTING_AVX512_DL_OPTIMIZE sources/openairinterface5g-v26.w14 configs/gnb scripts/gnb docs/` |

Do **not** reuse these tags for DL-optimize edits:

| Tag | Keep for |
|---|---|
| `PORTING_AVX512_CPU` | ISA / cores / PCI / NUMA / build flags only ([porting_avx512_du.md](porting_avx512_du.md) §0) |
| `__PORTING_TM_MODE__` | phy-test / TM3.1a features |
| `__PORTING_E2E__` | prior E2E AMC / TDA / attach work |

**C / C++** — keep the original under `#else`. Gate on the single macro (`=1` when `--dl-optimize`, else `=0`):

```c
#if PORTING_AVX512_DL_OPTIMIZE /* LATUAN 2026.10.19 PORTING_AVX512_DL_OPTIMIZE */
    /* new DL-optimize path */
#else /* HAVE LATUAN PORTING_AVX512_DL_OPTIMIZE */
    /* original */
#endif /* HAVE LATUAN PORTING_AVX512_DL_OPTIMIZE */
```

Local force-on (debug only; do not commit as the campaign default):

```c
#if 1 /* LATUAN 2026.10.19 PORTING_AVX512_DL_OPTIMIZE */
```

One-line add (no original to keep):

```c
/* PORTING_AVX512_DL_OPTIMIZE */ /* HAVE LATUAN 2026.10.19 */
```

**Shell**

```bash
# PORTING_AVX512_DL_OPTIMIZE /* HAVE LATUAN 2026.10.19 */
...
# endif PORTING_AVX512_DL_OPTIMIZE /* HAVE LATUAN 2026.10.19 */
```

**Conf / systemd** (key that changed)

```text
# PORTING_AVX512_DL_OPTIMIZE /* HAVE LATUAN 2026.10.19 */
  dl_bler_target_upper = .05;
# endif PORTING_AVX512_DL_OPTIMIZE /* HAVE LATUAN 2026.10.19 */
```

### Build option (deep OAI source patches — **default ON**)

`./build.sh --gnb-only` and `gnb_manager.sh build-gnb` enable DL-optimize by default.

| How | Command / knob |
|---|---|
| Default | `PORTING_AVX512_DL_OPTIMIZE=ON` → compile macro `=1` |
| Opt out CLI | `./scripts/gnb/gnb_manager.sh build-gnb --no-dl-optimize` |
| Opt out env | `PORTING_AVX512_DL_OPTIMIZE=0 ./scripts/gnb/gnb_manager.sh build-gnb` |
| CMake | `-DPORTING_AVX512_DL_OPTIMIZE=OFF` → macro `=0` (stock `#else`) |

Also applies to `build` / `build-all`. Rebuild and reinstall the DU binary after flipping the flag.

When a tagged block lands, add one line under §5 Result notes: date, files, and `grep` hit count.

---

## Status (2026-10-19 21:42 KST) — campaign best = **P1** (~967 MAC); target **stable 950**

| Item | Value |
|---|---|
| Phase | **Keep P1** (CORESET0=4, TDA 1+9, DMRS pos1, `dl_max_mcs=26`). P2 FAIL. Path to stable 950 / ~1G: RF then optional MCS27 |
| Env | `monolithic-e2e`, `MODE_IDX=3`, `DU_EXTRA_ARGS=` empty |
| Best measured | E2E-P1 @ 18:28: MAC **~967**, LCID4 **~965**, MCS26, CQI15, RI4, BLER ~0.04, TDA **1+9** |
| Prior settle (P0 TDA) | E2E-924c @ 17:58: iperf **~880**, MAC **~908** @ TypeA **2+8** (before CORESET0=4) |
| Live caution (21:33) | Conf had **drifted** (`force_256qam_off=1`, `dl_max_mcs=27`, RI=2) — restore P1 knobs before claiming regression |
| Theory @ MCS26 + P1 TDA | ~1000 MAC zero-BLER; live ~965 with ~4% retx |
| vs hist. 924 / LGE ~950 | P1 MAC already **above** 924/950 MAC; stable **950 iperf** needs RI4 + BLER&lt;0.03 (see § Recipe) |
| Why not MCS 27 yet | Hunt 26↔27 when uncapped; retry only after RF (P5) |
| Why `ul_max_mcs=10` | Protect DL HARQ; **P4 is UL-only** |
| Source | No must-fix DL hole left; optional CSI hysteresis only — see § Source |

### Prior: E2E-924c (2026-10-19 17:58 KST) — pre-P1 settle `dl_max_mcs=26` (~880 iperf)

| Item | Value |
|---|---|
| Process | PID **2721721**, ActiveEnter **17:54:44** |
| Live knobs | `force_256qam_off=0`, `dl_bler` 0.03/0.05, `dl_max_mcs=26`, `ul_max_mcs=10`, CORESET0 still **0** (TDA 2+8) |
| UE | RNTI **3e76**, RSRP **−54**, CQI **15**, RI **4** |
| Rate | iperf **~880**; MAC **~908** / LCID4 **~906** (14 s) |
| Note | Ceiling for **2+8** + 3 DMRS; superseded by P1 for rate |

### Prior: E2E-924a (2026-10-19 16:52 KST) — first 924 knobs + ~1G iperf

| Item | Value |
|---|---|
| Phase | 256QAM up; short of hist. 924 |
| Process | PID **2047602**, started **16:43:05** |
| Live knobs | `force_256qam_off=0`, `dl_bler` 0.03/0.05, `dl_max_mcs=27`, `ul_max_mcs=10` |
| UE | RNTI **c05d**, RSRP −67, CQI **13**, RI 4 |
| DL PHY | MCS **23**, Qm 8, NPRB 273, `dlsch_errors` 1, BLER ~0.015–0.031 |
| Rate (5 s) | MAC **~763**, LCID4 ~761, L1 ~789 |
| Gap then | MCS 23 vs 24; CQI 13 vs 15; BLER on climb gate |

### Why E2E does not reach MCS 27 (updated 2026-10-19 17:58)

E2E operating MCS is **not** `dl_max_mcs`. It is:

```text
MCS = min( BLER outer-loop MCS , CQI→dl_max_mcs ceiling , conf dl_max_mcs )
```

| Mechanism | Role | E2E-924a (16:52) | E2E-924c (17:54, settled) |
|---|---|---|---|
| Conf `dl_max_mcs` | Soft allow-list | **27** | **26** (cap after hunt) |
| CQI → `get_mcs_from_cqi()` | CSI ceiling | CQI **13** | CQI **15** (no longer the limiter) |
| `get_mcs_from_bler()` 0.03/0.05 | Outer loop | Hang at MCS **23** | At cap **26**: BLER≈0; with allow **27**: hunted 26↔27, BLER 0–7% |
| Phy-test `-m 27` | Fixed MCS | n/a | Still not proof for E2E RI4 |

| Point | MCS | CQI | RSRP | Rate | Notes |
|---|---|---|---|---|---|
| E2E-924a | **23** | **13** | −67 | ~763 MAC | First 924 knobs |
| E2E mid (RF closer) | **25** | **15** | ~−51 | ~878 | Channel recovered |
| E2E `dl_max=27` hunt | **26↔27** | **15** | −54 | unstable BLER | AMC edge, not CQI drop |
| **E2E-924c (now)** | **26** | **15** | **−54** | **~908 MAC / ~880 iperf** | Cap 26; BLER≈0 |
| Hist. best E2E-256e | **24** | **15** | — | ~924 MAC | retx 3.6%, BLER 0.042 |
| DL phy-test | **27** | n/a | — | ~1260 L1 | Forced; RI 1 |

**Implications (settled)**

- CQI **15** achieved; limiter is no longer CSI — it is **MCS27 air reliability @ RI4 / 273 PRB**.
- Keep **`dl_max_mcs=26`** as the stable E2E point (~880 iperf / ~908 MAC). Do **not** widen BLER gate or remove CQI ceiling.
- At MCS26 with **current OAI TDA+DMRS**, MAC is at **this stack’s** ceiling (~905–908). **Not** a DDSUU/RU limit: LGE ~950 with same RU and mixed **2+8**. Next lever = full-D DMRS/CORESET (2 vs 3 DMRS symb), not mixed 1+9.
- `ul_max_mcs=10` (not 16): deliberate DL-HARQ protection; optional to raise for UL iperf only — will not close the DL gap.
- Code refs: `gNB_scheduler_uci.c`, `get_mcs_from_bler()` / `get_mcs_from_cqi()` in `gNB_scheduler_primitives.c`, `gNB_scheduler_dlsch.c`.

### Theory max @ MCS 26 (2026-10-19 18:05) — OAI formula + live TDA

**Inputs (live conf + OAI)**

| Param | Value | Source |
|---|---|---|
| Cell | n79 100 MHz, **273 PRB**, SCS **30 kHz** (slot 0.5 ms) | `002…4x4.conf` |
| TDD | DDSUU: `nrofDownlinkSlots=2`, mixed `nrofDownlinkSymbols=10` / UL sym 2, `nrofUplinkSlots=2` | period **5 slots = 2.5 ms** → **400** periods/s |
| DL opportunities | **2×D + 1×S** per period → **1200** PDSCH/s | live `dlsch` newTX **1200/s** (100%) |
| MIMO / MCS | RI **4**, MCS table **1**, MCS **26** | `Table_51312[26]` = **Qm 8**, **R 9165** (916.5/1024) |
| TBS API | `nr_compute_tbs(Qm,R,nb_rb,nrOfSymbols,N_PRB_DMRS*N_DMRS_SLOT,…,Nl)` → bits; MAC uses `>>3` bytes | `nr_compute_tbs_common.c` |
| DMRS (L=4) | Type1, `numDmrsCdmGrpsNoData=2` → **N_PRB_DMRS=12**; TypeA + `dmrs_TypeA_Position=pos2` + additional pos1 | `get_dl_dmrs_params()` |

**Live TDA (what is actually scheduled)**

| Slot | TDA | Mapping | Symbols | DMRS RE/PRB | TBS (bytes) | Evidence |
|---|---|---|---|---|---|---|
| Full **D** | **0** | TypeA | **2+12** (`len_coreset=2`) | **36** (12×3 symb) | **106587** | OAI `nr_compute_tbs`; matches inferred ~107041 from MAC avg |
| Mixed **S** | **2** | TypeA | **2+8** | **24** (12×2) | **69677** | `du.log`: `mixed S PDSCH: TDA=2 map=A sym 2+8 … TBS=69677 MCS=26 L=4` |
| CSI-RS | 1 | TypeA | 2+11 (when `sched_csirs`) | — | slightly lower | `get_dl_tda()` returns 1 |

Why **2+8** not hist. **1+9**: `nr_rrc_config_dl_tda()` builds only TDA **0/1/2** (`list.count=3`). `get_dl_tda_for_ue()` would pick TypeB **TDA3** only if `count > 3` — **never true** on this binary. Mixed stays CORESET0-safe TypeA **2+8**.

**Peak MAC (zero BLER, 273 PRB every DL slot)**

```text
MAC_bps = (2 × TBS_D + 1 × TBS_S) × 8 × 400
        = (2 × 106587 + 69677) × 8 × 400
        = 905.1 Mbit/s
```

| Layer | Theory | Measured (E2E-924c) | Notes |
|---|---|---|---|
| MAC TX | **~905 Mbit/s** | **~908 Mbit/s** | Within ~0.3% (CSI-RS mix / sample); **carrier saturated** |
| PDSCH/s | 1200 | **1200** | 100% of DDSUU DL slots |
| App (iperf) | ~905 × 0.97 ≈ **~880** | **~880** | ~3% RLC/PDCP/IP — matches |

**Verdict (OAI stack today):** MCS **26** + TypeA **2+12/2+8** + **3 DMRS on full D** → **~905–908 MAC / ~880 iperf** is the ceiling **for this binary**. Carrier already 100% scheduled.

**Correction vs LGE ~950 (same RU, still DDSUU, mixed still 2+8):**  
Mixed **1+9 is not required**. Same pattern + **2+8** can clear ~950 if full-D overhead is lighter than OAI’s 3-DMRS TypeA pos1:

| Config (still DDSUU, S=**2+8**) | TBS_D / TBS_S | MAC @ MCS26 | Notes |
|---|---|---|---|
| **OAI now** — D 2+12, **3 DMRS** (36 RE) | 106587 / 69677 | **~905** | Matches live ~908 |
| D 2+12, **2 DMRS** (24 RE) | 116769 / 69677 | **~970** | Enough for **~950** app/MAC |
| D 1+13, 2 DMRS | 129024 / 69677 | **~1049** | If CORESET only 1 sym on full D |
| OAI TDA + MCS **27** (3 DMRS D) | 108573 / 73766 | **~931** | Still short of 950; BLER hunt when tried |

So gap to LGE is likely **full-D DMRS count / CORESET start**, not RU pattern and not mixed 1+9.

**What-if (optional; not needed to explain LGE 950)**

| Change | Approx MAC @ MCS26 | Comment |
|---|---|---|
| Keep **2+8**, reduce full-D DMRS 3→2 | **~970** | Primary path toward LGE-class |
| Mixed TypeB **1+9** (extra) | **~947** with heavy D | Secondary; hist. path, not required if DMRS fixed |
| MCS **27** stable | ~931 with current DMRS | Needs RF; did not hold BLER here |

### Prior: E2E-pre924 (2026-10-19 16:41 KST) — before 924 conf

| Item | Value |
|---|---|
| Phase | E2E baseline pre-upgrade; ~1G offer |
| PID | 1900029; `force_256qam_off=1`, BLER 0.05/0.15, `ul_max_mcs=16` |
| Air | MCS 26 / Qm **6** / RI 4 / ~**653** Mbit/s MAC |

### Prior live snapshot (2026-10-19 16:04 KST) — TM3.1a-dlopt

| Item | Value |
|---|---|
| Phase | **TM3.1a + DL-optimize binary** — slot clock **clean**; first `PORTING_AVX512_DL_OPTIMIZE` patch verified |
| Live file | `/etc/oai-gnb/conf/gnb.conf` (Keysight TM3.1 256-QAM 4×4 independent-stream DDSUU) |
| Env | `DEPLOY_PROFILE=monolithic-tm`, `MODE_IDX=2`, `DU_EXTRA_ARGS="-l 4"`, `THREAD_POOL=11-15,32-38` |
| Process | PID **1645348**, started **16:01:01**. `--phy-test -l 4 --thread-pool 11-15,32-38` |
| Binary | `/opt/oai-gnb/bin/nr_softmodem` mtime **15:59**, Branch `avx512` hash `f4be9572c`. **Contains** `skip_rx: RX slot still busy` → macro `=1` build |
| Services | `oai-du` **active**, `oai-gnb-env` **active** (CU-CP/CU-UP inactive — expected for monolithic-tm) |
| Live knobs | `force_256qam_off=0`, `dl_min_mcs=dl_max_mcs=27`, `link_direction=dl`, `independent_stream_mode=1`, `dl_tx_eaxc_mask=15`, `dl_mcs=27`, `dl_bw=273` |
| PHY (L1) | Qm **8**, RI **1**, 273 PRB, `dlsch_errors=0`. L1 TX **~1259 Mbit/s** (3 s @ 16:04) |
| MAC | RNTI **1234**, UL rounds 0 (DL-only) |
| `du.log` | size 9108, mtime 16:01:07 — **0** slot mismatch, **0** frame mismatch, **0** PUCCH-past, **0** SR fail (stable ~3 min) |
| CPU | FH cores 5/6/7 ~99%; `L1_tx_thread` ~86%; Tpool ~9% — same load shape, clock no longer jumps |
| DL optimize | **ON by default** (`./build.sh --gnb-only` / `build-gnb`) |

TM3.1a guide: [oai_tm3_1a_test_guide.md](oai_tm3_1a_test_guide.md).

### Solution applied (slot +3 jump)

**Problem (TM3.1a-orig, 15:31, PID 1273721):** `ru_thread` called `wait_free_rx_tti()` on UL/mixed slots even in DL-only phy-test. That ~2 ms wait let the FHI RX queue hit `MAX_QUEUE_LENGTH_NO_JUMP` (3) → continuous **+3** slot/frame mismatch; PUCCH-in-past and `Cannot schedule SR` were fallout.

**Fix (compile-gated, default ON):**

| File | Change |
|---|---|
| `sources/openairinterface5g-v26.w14/CMakeLists.txt` | Option `PORTING_AVX512_DL_OPTIMIZE` **default ON** → single macro `PORTING_AVX512_DL_OPTIMIZE=1\|0` (no twin `__PORTING_*__`) |
| `scripts/gnb/gnb_manager.sh` | Default `dl_optimize=1` for `build-gnb` / `build-all`; `--no-dl-optimize` or env `=0` for stock path |
| `sources/.../executables/nr-ru.c` | Under `#if PORTING_AVX512_DL_OPTIMIZE`: DL-only phy-test (`phy_test && ulsch_slot_bitmap==0`) **skips** `wait_free_rx_tti` + `feprx`; FHI E2E/UL non-RFsim **skip_rx** if RX buffer still busy; RFsim keeps original wait. Original under `#else` |

**Verify:** binary string `skip_rx: RX slot still busy` present; after DU restart 16:01, mismatch counts stay **0** while L1 stays ~1260 Mbit/s.

### Config for E2E ~924 (project directory, 2026-10-19) — no new OAI source

Align with `~/backup/e2e.900M.20261015-185722/` knobs. User builds image and deploys.

| File | Change |
|---|---|
| `configs/gnb/002.gnb.sa.e2e.band79.100mhz.273.fhi72.4x4.conf` | `force_256qam_off` **0**; `dl_bler_target_lower/upper` **0.03 / 0.05**; `dl_max_mcs` **26** (was 27; stop 26↔27 hunt); `ul_max_mcs` **10** (was 16; hold UL for DL HARQ). Tagged `PORTING_AVX512_DL_OPTIMIZE`; originals kept as `#` commented lines |
| `configs/gnb/env/oai_gnb_fhi72_env.conf` | Confirm `DEPLOY_PROFILE=monolithic-e2e`, `MODE_IDX=3`, `DU_EXTRA_ARGS=` (empty). Comment stamp for E2E-924 path |

**Deploy reminder:** install that conf as live `gnb.conf`, restart **`oai-du` only**. Expect after attach: Qm 8, RI 4, MCS ~24, MAC TX toward **924**. Source (TDA/AMC) already in tree — touch only if this config re-measure fails.

### Earlier issue snapshot (TM3.1a-orig, kept for compare)

At 15:33 on stock path (macro `=0` / pre-patch binary): slot mismatch **9958**, frame **2169**, PUCCH past **5000**, SR fail **4633**; last 280 slot deltas all **+3**.

### Design concerns — skip vs wait, UL/E2E, ACC, “absolute” fix (2026-10-19)

Logged from lab review after TM3.1a-dlopt. Keep this when reconsidering the policy.

#### Why stock blocks at all

`wait_free_rx_tti` waits until `rx_tti_busy[slot % RU_RX_SLOT_DEPTH]` clears so `feprx` does **not overwrite** an RX buffer L1 is still decoding. Blocking protects **data integrity**, not because FHI requires a wait. On RFsim (no hard fronthaul deadline) blocking is reasonable. On **FHI 7.2** a long block stalls `ru_thread` while xRAN RX keeps enqueueing → queue hits cap 3 → **+3** clock jump.

**L1 behind realtime:** radio time (FHI) already moved to a new slot while L1 has not finished the older slot that still owns that buffer index. Then you must choose: wait (risk clock jump) or skip that UL (lose one TTI, keep clock).

#### Behaviour by mode (same `#if PORTING_AVX512_DL_OPTIMIZE`)

| Mode | Policy | Effect |
|---|---|---|
| **DL phy-test** (`phy_test` + `ulsch_slot_bitmap==0`) | Always skip wait + skip `feprx` | No UL work → waiting is pure waste. **This fixed TM3.1a.** |
| **UL phy-test / E2E** on FHI | If buffer free → mark busy + `feprx`; if still busy → **`skip_rx` one UL slot** | Real UL kept when on time; under overload drop one UL TTI instead of jumping the cell clock |
| **RFsim** | Original blocking `wait_free_rx_tti` | Unchanged |

So the patch is **not** “DL-test only” in the binary; only the **always-skip** branch is DL-test-only. E2E/UL use non-blocking skip-when-busy.

#### Is the current solution “optimal”? Absolute guarantee?

- **Optimal for this lab stage:** yes as a **clock-safety baseline** (proven on TM3.1a; safer default for FHI E2E than unbounded wait).
- **Not absolute:** no finite realtime system can guarantee **both** zero clock jumps **and** zero UL drops under unbounded load. Absolute would need L1 always finishing before deadline (ACC, more RX cores, admission control) **and/or** a deeper split of FHI timing from L1 completion.
- **Keep current policy** as the floor; improve “L1 on time” next (ACC, cores) to **reduce how often** skip fires — do not go back to unbounded wait.

#### ACC100 LDPC offload

| Case | ACC helps? |
|---|---|
| DL phy-test jump | **No** — no UL decode involved |
| E2E/UL when bottleneck is LDPC/HARQ | **Yes** — frees `rx_tti_busy` sooner → fewer skips |
| Bottleneck is `feprx` / FH / equalize | **No** — ACC does not touch those |
| Removes need for skip policy? | **No** — still need a late-slot policy if anything else runs over budget |

#### Concern: why not wait ~1 ms first, then skip?

Raised in review: prefer a short wait before giving up.

| Idea | Assessment |
|---|---|
| Wait **1 ms** then skip | **Not safe on this cell.** Slot at SCS 30 kHz ≈ **0.5 ms**; 1 ms ≈ **2 slots** — same order as the ~2 ms stall that caused +3 jumps. FHI RX still fills during that wait. |
| Wait **tens–~100 µs** then skip | Plausible **future hybrid** for E2E: recover UL when L1 is almost done, without multi-slot stalls. Needs measurement (mismatch rate vs `skip_rx` count). |
| DL-only | Any wait is pointless — keep always-skip. |

**Decision for now:** keep immediate skip-when-busy on FHI E2E/UL; do **not** adopt a 1 ms pre-wait. Optional follow-up: bounded wait in **µs**, not ms, behind the same `PORTING_AVX512_DL_OPTIMIZE` gate after E2E numbers exist.

#### Verdict

Prefer **lose one UL slot** over **break cell timing**. Current patch encodes that. Next gains come from making L1 finish on time (ACC, RX capacity), not from restoring long blocking waits.

---

## Known prior baseline (do not treat as this campaign)

From [du_max_throughput_tracking.md](du_max_throughput_tracking.md) / `~/backup/e2e.900M.20261015-185722/`:

| Mode | Date | Result | PHY snapshot |
|---|---|---|---|
| DL phy-test 4 eAxC | 2026-10-15 | MAC TX **~1350 Mbit/s**, log clean after RX-wait skip | MCS 27, Qm 8, RI **1**, 273 PRB |
| E2E 256QAM best | 2026-10-15 18:31 | MAC TX **924 Mbit/s** (8 s) | MCS 24, Qm 8, RI 4, 273 PRB, retx 3.6%, BLER 0.042 |
| Gap to ~950 | — | Needs ~MCS 25 with flat retx | At MCS 24 the 5% drop gate holds the loop |

Restore bundle (when E2E optimize actually starts — **not now**):

```text
~/backup/e2e.900M.20261015-185722/{gnb.conf,oai_gnb_fhi72_env.conf,nr_softmodem}
```

Do **not** replace `/opt/oai-gnb/lib/libxran.so`. Do **not** restart `oai-gnb-env` (tears down VFs).

---

## 1. Cell / test matrix

| Item | Value |
|---|---|
| Band / BW | n79, 100 MHz, 273 PRB, SCS 30 kHz |
| MIMO | 4×4 (`maxMIMO_layers = 4`) |
| TDD | DDSUU, O-RU pattern-id **0** |
| Fronthaul IQ | `iq_width = 9`, `iq_width_prach = 16` |
| First gate | TM3.1a original + dlopt — **both done** (jump fixed) |
| E2E settle | **Keep P1** (~967 MAC, CORESET0=4, TDA 1+9, DMRS pos1). **P2 FAIL** — do not retry |
| Next | Restore live knobs to P1 if drifted; RF (P5) → optional MCS27 (P3) for ~1G; see § Source + § Toward 1G |

---

## 2. What to copy every run

Steady second of `du.log` / `nrMAC_stats.log` (not ramp):

- DL: MCS, Qm, layers/RI, PRB, HARQ retx, BLER, CQI (E2E only)
- MAC TX Mbit/s (3–10 s sample) and/or iperf receiver average
- Slot mismatch rate (should stay ~0 after prior clock fixes)
- CPU: `fh_main_poll` / `fh_rx_bbdev` / `fh_cp_gen` / `L1_tx_thread` / `ru_thread`
- Binary string: `Branch:` / `Abrev. Hash:` from `nr_softmodem`

Qm 6 = 64QAM. Qm 8 = 256QAM.

---

## 3. Run log

| Run | Date | Mode | Profile / knobs | Mbps | MCS | Qm | RI | PRB | Retx / err | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| TM3.1a-orig | 2026-10-19 15:31 | TM3.1a phy-test | mask 15, `-l 4`, MCS 27, stock path | **~1261** (L1, 3 s) | 27 | 8 | 1 | 273 | errors 0 | PID 1273721. **+3 jump** (9958 slot / 2169 frame). PUCCH past + SR fail. FH ~99%, L1 TX ~88% |
| TM3.1a-dlopt | 2026-10-19 16:01 | TM3.1a phy-test | same conf; binary w/ `PORTING_AVX512_DL_OPTIMIZE=1` | **~1259** (L1, 3 s) | 27 | 8 | 1 | 273 | errors 0 | PID **1645348**. Log **clean** (0/0/0/0). `skip_rx` in binary. FH still ~99%, L1 TX ~86% |
| E2E-pre924 | 2026-10-19 16:41 | E2E | 64QAM / BLER 0.05–0.15 / ul_max 16; ~1G offer | **~653** MAC (3 s) | 26 | **6** | 4 | 273 | err 0, BLER ~0.0005 | PID 1900029, RNTI cf00, CQI 14. Clock clean |
| E2E-924a | 2026-10-19 16:52 | E2E | **924 knobs**; `dl_max=27`; ~1G offer | **~763** MAC / ~789 L1 (5 s) | **23** | **8** | 4 | 273 | err 1, BLER ~0.015–0.031 | PID **2047602**, RNTI c05d, CQI **13**, RSRP −67. Clock clean |
| E2E-924b | 2026-10-19 ~17:30 | E2E | same knobs; RF closer (~80 cm) | **~878** (approx) | **25** | **8** | 4 | 273 | low | CQI **15**, RSRP ~−51. Channel recovered; still under hist. 924 |
| E2E-mcs27 | 2026-10-19 ~17:45 | E2E | `dl_max_mcs=**27**` | unstable | **26↔27** | **8** | 4 | 273 | BLER **0–7%** | CQI 15 flat — hunt is AMC edge, not CSI |
| E2E-924c | 2026-10-19 17:54 | E2E | `dl_max_mcs=**26**` (live+project) | **~880** iperf / **~908** MAC (14 s) | **26** | **8** | 4 | 273 | err 0, BLER ~0–0.003 | PID **2721721**, RNTI **3e76**, RSRP **−54**, CQI **15**. CSI/MCS flat 20 s. **Settled** |
| E2E-P1 | 2026-10-19 18:28 | E2E | CORESET0 **4**; `dl_max=26` | **~967** MAC / ~965 LCID4 (20 s) | **26** | **8** | 4 | 273 | err 0, BLER ~0.03–0.047 | PID **3010176**, RNTI **a2c6**. TDA **1+9** TBS 81975. RSRP−54 CQI15 flat. +59 vs P0 |
| E2E-P2 | 2026-10-19 18:51 | E2E | P1 + DMRS **pos0** | **~609** MAC (20 s) | **18–25** | **8** | 4 | 273 | err 6, BLER 0.03–0.20, retx ~31% | PID **3160153**, RNTI **aa4f**. TDA 1+9. **Worse — revert pos1** |
| E2E-opt-1 | | E2E | one knob | | | | | | | |

---

## 4. Optimize order

| Step | Change only this | Expect if it was the limiter |
|---|---|---|
| 0 | TM3.1a original (stock path) | **Done (noisy):** ~1261 Mbit/s; +3 jump |
| 0b | Rebuild with `PORTING_AVX512_DL_OPTIMIZE=1` (`nr-ru.c` wait skip) | **Done (clean):** ~1259 Mbit/s; 0 mismatches @ 16:04 |
| A0 | Project conf → 924 E2E knobs (no new OAI source) | **Done in repo** 2026-10-19 — see § Config for E2E ~924 |
| A | Deploy E2E 924 knobs + re-measure | **Done (partial):** Qm 8 / RI 4 / MCS 23 / ~763 MAC @ 16:52 — short of 924 |
| B | (done) `force_256qam_off` 0 | Qm **8** confirmed |
| C | (done) BLER 0.03 / 0.05 | MCS at 23; BLER ~0.015–0.03 hangs near climb edge |
| D | RF → CQI 15; try `dl_max` 25→27→**26** | **Done:** CQI15; MCS27 hunt unstable; **cap 26** → ~880 iperf / ~908 MAC, BLER≈0 |
| E | Rank / CSI only if RI &lt; 4 | RI **4** already — not the limiter |
| F | Leave `iq_width = 9` | RU rejects data 16-bit |
| G | Optional: `ul_max_mcs` 10→16 | UL-only; does **not** raise DL rate |
| H | Optional: RF / lab for stable MCS27 | Only if need &gt;910 without retx swing |
| I | Full-D **DMRS 3→2** (or CORESET1 / start earlier) keep mixed **2+8** | Theory → **~970** MAC @ MCS26 — path to LGE-class ~950 without changing RU/DDSUU |
| J | Optional: mixed TDA3 **1+9** | Extra headroom; **not** required to explain LGE 950 @ 2+8 |

### Next trials (2026-10-19) — further optimize, stability first

**Hold baseline:** `dl_max_mcs=26`, BLER 0.03/0.05, `ul_max_mcs=10`, DDSUU / RU pattern-id 0, DL-opt binary. **One knob per run.** Pass = attach OK + stable BLER + iperf ≥ baseline + clean clock. **No RU change** for any Pn below.

| # | Trial | Change | Expect | Risk / abort |
|---|---|---|---|---|
| **P0** | **Hold baseline** | None | ~880 iperf / ~908 MAC, BLER≈0 | Stable rollback target (pre-P1) |
| **P1** | CORESET0 **1 symb** | `initialDLBWPcontrolResourceSetZero` **0 → 4** (or 5) | TDA **1+13 / 1+9**; MAC ↑ (~970–1080 depending on DMRS) | Attach/SIB1 fail → revert **0** immediately. Do not try index 9 |
| **P2** | DMRS **pos0** | `dmrs_AdditionalPosition` pos1→pos0 | *(tried)* Theory ~970 | **FAIL 18:51** — MAC~609, revert pos1 (`#if 0`) |
| **P3** | Retry MCS27 (after P1) | `dl_max_mcs` **26 → 27** | Extra few % if RF holds | BLER hunt 26↔27 → back to **26** |
| **P4** | Raise UL cap | `ul_max_mcs` **10 → 16** | UL iperf ↑; **no** DL gain expected | DL HARQ/DTX worse → back to 10 |
| **P5** | RF only | Distance / TX power / antennas | Keep CQI15; lower BLER for MCS27 | No conf change if already stable |

#### Trial rationale (evidence → hypothesis)

| # | Why try | Evidence / theory | Hypothesis to verify |
|---|---|---|---|
| **P0** | Safe compare + rollback | Live: MCS26, CQI15, BLER≈0, 1200 PDSCH/s, ~908 MAC = OAI ceiling with 3 DMRS on D | Later Pn must not be less stable than P0; rate gains only if BLER stays healthy |
| **P1** | More PDSCH REs **without RU change** — CORESET0 at 2 symb was the TDA limiter | Conf `controlResourceSetZero=0` → Table 13-6 → **2 symb** → TDA **2+12/2+8**. Index **4/5** → **1 symb** → TDA **1+13/1+9**. Hist. 924 used long TDA | Attach OK + log `sym 1+9` + MAC > 908. SIB1 fail → index incompatible with SSB 717216 |
| **P2** | Explain LGE ~950 **same RU + still 2+8** | OAI full-D **3 DMRS** (36 RE) → MAC~905; **2 DMRS** (24 RE) same 2+8 → MAC~**970**. `dmrs_AdditionalPosition=pos1` in `nr_radio_config.c` | pos0 cuts N_DMRS_SLOT on D; TBS_D↑; mixed stays 2+8; BLER not worse than P0 — **disproved on air** |
| **P3** | One MCS step left after RE/DMRS headroom | MCS27 R=9480; ~931 MAC on old TDA; CQI15 ceiling OK but AMC hunted at cap=27 | After P1 (longer TDA), MCS27 may hold without 0–7% BLER swing |
| **P4** | UL was capped to protect DL HARQ — maybe too tight | `ul_max_mcs=10` intentional (prior DTX storm). Live UL SNR~11 dB, BLER0 @10 — room to try 16 **without changing DL theory** | UL iperf↑; DL MAC/BLER/PUCCH unchanged. If DL worsens → cap 10 still required |
| **P5** | Prior MCS27 fail was **air**, not a missing knob | CQI15 flat during 26↔27 hunt → RF edge for MCS27 @ RI4/273 PRB | Better SNR → P3 passes; no conf needed |

**Do not do (rejected + why):**

| Action | Why rejected |
|---|---|
| Widen BLER gate 5%/8% | Caused RLF / high retx; does not raise RE budget |
| Remove CQI ceiling | MCS overshoots channel → BLER/RLC full |
| Change RU / TDD pattern | Not needed for P1–P5; LGE 950 on same RU |
| Require mixed 1+9 before DMRS trial | LGE ~950 still on 2+8; 1+9 is a P1 outcome, not a prerequisite vs LGE |

**Suggested order:** Record P0 → **P1** (conf-only, easy revert) → if attach fails then **P2** was next (now **failed** — skip) → **P3**. P4 independent (UL). P5 anytime in parallel.

**Pass criteria per run:** RSRP/CQI stable 20 s; MCS not hunting; BLER ≪ 0.03; PDSCH ~1200/s; iperf + MAC sample; `du.log` 0 slot jump.

#### P1 run status (2026-10-19 18:25–18:28) — **PASS (rate↑, TDA OK)**

| Item | Value |
|---|---|
| Change | `initialDLBWPcontrolResourceSetZero` **0 → 4** |
| Project + live | both **=4**; DU restart **18:25:28**, PID **3010176**, RNTI **a2c6** |
| TDA (goal) | mixed **`sym 1+9`** map=A, TBS_S **81975** @ MCS26 L=4 — **confirmed** in `du.log` |
| 20 s @ 18:28 | RSRP **−54** flat, CQI **15** flat, MCS **26** flat, NPRB 273, `dlsch_errors` **0** |
| Rate (20 s) | MAC TX **~967** Mbit/s, LCID4 **~965**; newTX **~1150**/s (retx Δ **~961**/20 s ≈ 4%) |
| BLER | **~0.029–0.047** (higher than P0 ≈0; near 0.05 drop gate — watch) |
| vs P0 | MAC **908 → 967** (+~59); TDA **2+8 → 1+9**; still short of LGE ~950 app / theory ~1009 zero-BLER |
| Next | **Keep P1**; P2 **reverted in source** (`#if 0`) — rebuild/deploy pos1 to restore ~967; optional P3 only if BLER &lt;0.03 |
| Abort P1 | `=0` + restart if attach/BLER unstable |

#### Live conf backup (2026-10-19 18:32)

```text
~/backup/e2e.p1-coreset4.20261019-183235/
  gnb.conf, oai_gnb_fhi72_env.conf, etc-oai-gnb-conf/, knobs.grep.txt, README.txt
```

P1 live (`controlResourceSetZero=4`, `dl_max_mcs=26`). Restore: copy `gnb.conf` → `/etc/…` then `restart oai-du` only (do **not** restart `oai-gnb-env`).

#### P2 run status (2026-10-19 18:31–18:52) — **FAIL (worse than P1) → revert**

| Item | Value |
|---|---|
| Change | TypeA `dmrs_AdditionalPosition` **pos1 → pos0**; binary 18:33; FH fixed (VF MAC) @ ~18:41 |
| Stack with P1 | `controlResourceSetZero=4`, TDA **1+9** still on |
| 20 s @ 18:51 | RNTI **aa4f**, RSRP −54, CQI **15**, MCS **18↔25** hunt, BLER **0.03–0.20**, err **6** |
| Rate | MAC **~609** / LCID4 **~607**; newTX ~868/s; **retx ~31%** |
| vs P1 | MAC **967 → 609** (−~37%); BLER was ~0.04 @ MCS26 stable → now unstable |
| Verdict | **pos0 too thin for RI4 / long TDA** on this channel. **Revert P2** (pos1); **keep P1** |
| Source | `nr_radio_config.c`: P2 block set to **`#if 0`** (pos1 active again after rebuild) |

##### Why P2 was worse (analysis)

Fewer DMRS RE ≠ higher goodput when channel estimation fails.

| | P1 pos1 | P2 pos0 |
|---|---|---|
| TDA | 1+9 | 1+9 (same) |
| CQI / RSRP | 15 / −54 | 15 / −54 (**RF unchanged**) |
| MCS | **26** stable | **18↔25** AMC hunt |
| BLER / retx | ~0.04 / ~4% | **0.03–0.20 / ~31%** |
| MAC | **~967** | **~609** (−37%) |

Mechanism: `pos0` drops additional DMRS on long TypeA (1+13/1+9) at **RI 4** + 256QAM → richer TBS momentarily but **worse equalizer** → NACK↑ → AMC drops MCS + HARQ burns airtime (`newTX ~868/s` vs ~1150) → net rate falls. CQI stayed 15 → not an RF drop; **reference-signal budget** was the fault. LGE ~950 @ 2+8 may use light DMRS only with different RF/UE — **do not copy pos0** here. Keep **P1 + pos1**.

```bash
# After source revert (#if 0 → pos1): rebuild, deploy, restart oai-du ONLY
# Keep initialDLBWPcontrolResourceSetZero = 4
# Verify VF MAC 8c:1f:64:41:ff:f9 BEFORE start (deploy once broke RX=0)
```

Earlier FH RX=0 (18:35): VF MAC random `36:88:…` vs expect `8c:1f:64:41:ff:f9` — fixed; orthogonal to DMRS quality.

### CSI / “CQI unstable” (2026-10-19 21:33, ~30 s sample)

Wideband **CQI was flat 15**. Perceived instability was **PMI + MCS + BLER**, and **RI=2** (not 4):

| Metric | Sample |
|---|---|
| CQI | **15** only |
| RI | **2** only (rate killer vs RI4) |
| PMI | jumped e.g. (9,0)…(15,1) |
| MCS | **16–24** (BLER-driven AMC) |
| BLER | **0.05–0.17** |
| Live conf drift | `force_256qam_off=**1**`, `dl_max_mcs=**27**` — **not** P1; restore P1 knobs first |

**Stabilize (priority):** (1) RF hold UE/ant → RI4 + lower BLER; (2) restore P1 conf (`256QAM on`, `dl_max=26`, CORESET0=4, pos1); (3) keep `do_CSIRS=1`. Optional later source: CQI/PMI hysteresis — see § Source. Do **not** widen BLER gate / remove CQI ceiling / retry pos0.

### Toward ~1 Gbps (2026-10-19 21:30)

| Target | Need |
|---|---|
| ~965–980 MAC | Already P1 @ MCS26 |
| ~1000 MAC | BLER≈0 @ MCS26 **or** MCS27 |
| **~1.0G iperf** | Essentially **MCS27 stable** on P1 TDA (+ RF); MAC ≳ 1030 |

Path: **keep P1** → **P5 RF** (BLER &lt;0.03, RI4) → **P3 `dl_max_mcs=27`** one 20 s trial → abort to 26 if hunt. **P4** (`ul_max_mcs` 10→16) is **UL-only** — does not raise DL. No free RE knob left like CORESET.

### Recipe: stable ~950 Mbps (2026-10-19 21:42)

**Best proven point:** P1 — CORESET0=4, TDA **1+9**, DMRS **pos1**, MCS **26**, MAC **~965–967** (already ≥950 MAC). Stable **950 iperf** needs the same knobs with **RI=4** and **low BLER** (app ≈ MAC × ~0.97).

1. **Lock P1 knobs** (fix live drift first): `force_256qam_off=0`, `dl_max_mcs=26`, BLER 0.03/0.05, `controlResourceSetZero=4`, DMRS pos1, `ul_max_mcs=10`. Restart **`oai-du` only**. Confirm `mixed S … sym 1+9`.
2. **RF (P5)** until 60 s pass: CQI15 flat, **RI=4** flat, MCS **26** flat, BLER **&lt;0.03**, MAC **≳950**, FH `rx`&gt;0.
3. **iperf 60 s average** + MAC same window. Pass = iperf **≥950** and MCS/BLER flat entire run.
4. If MAC≥950 but iperf short: improve RF further (BLER→0, MAC→980–1000) — no conf magic.
5. Only then careful **P3** (`dl_max_mcs=27`); **abort to 26** on 26↔27 hunt or BLER&gt;5%.

**Do not:** pos0, widen BLER gate, remove CQI ceiling, change RU/`iq_width`, or use P4 for DL.

### Source code assessment (DL) — 2026-10-19 21:37

**No remaining “must-fix” hole for DL rate.** Stack already carries E2E AMC/TDA/clock ports; ceiling is air + conf.

| Area | Status |
|---|---|
| `nr-ru.c` skip_rx / DL wait | Done — clock clean |
| `get_mcs_from_bler()` production AMC + poison reset | Done (`gNB_scheduler_primitives.c`) |
| CQI ceiling + HARQ-gated halfway seed | Done (`gNB_scheduler_uci.c`) |
| CORESET0→TDA start / P1 idx4 → 1+9 | Done (conf + `nr_radio_config.c`) |
| DMRS pos1 (pos0 `#if 0`) | Done — pos0 proven bad |
| TDA3 TypeB helper | In tree; P1 already schedules **1+9** TypeA |
| Optional: CQI/RI hysteresis, softer AMC near gate | Nice-to-have stability only — **won’t unlock 1G alone** |
| ACC / µs-wait FHI | UL realtime — not DL Mbps |

Do **not** reopen: pos0, ungated CQI→MCS, wide BLER 5%/8%, 1 ms FHI pre-wait.

Code paths:

- AMC: `get_mcs_from_bler()` — `gNB_scheduler_primitives.c`
- CQI: `evaluate_cqi_report()` — `gNB_scheduler_uci.c`
- TDA / mixed: `gNB_scheduler_dlsch.c`, `nr_radio_config.c`
- Clock: `nr-ru.c` (`PORTING_AVX512_DL_OPTIMIZE`)

---

## 5. Result notes

- TM3.1a-orig (2026-10-19 15:31, PID 1273721): Stock path. MCS 27 / Qm 8 / RI 1 / 273 PRB, L1 ~1261 Mbit/s, errors 0. Log noisy: +3 slot jump (9958/2169), PUCCH-past, SR fail. Cause: blocking `wait_free_rx_tti` on mixed/UL in DL-only phy-test.
- 2026-10-19 source/build: `PORTING_AVX512_DL_OPTIMIZE` default ON; CMake + `gnb_manager.sh` + `nr-ru.c` (`#if` / `#else` original). Opt out `--no-dl-optimize`. Grep tag hits across those files + this doc.
- TM3.1a-dlopt (2026-10-19 16:01–16:04, PID 1645348): Same conf, DL-optimize binary (mtime 15:59, `skip_rx` present). L1 ~1259 Mbit/s, Qm 8, RI 1, errors 0. **du.log clean** for ~3 min (0 slot / 0 frame / 0 PUCCH / 0 SR). Solution confirmed: DL-only skip of RX wait stops the +3 jump without hurting DL rate. FH cores still busy-poll ~99% (expected); not the clock limiter once wait is skipped.
- 2026-10-19 design concerns (see Status §): blocking exists to protect RX buffers; FHI late → skip beats jump; ACC helps UL LDPC only; no absolute zero-drop+zero-jump; **reject wait-1ms-then-skip** (≈2 slots @ 30 kHz); optional later: µs-bounded wait for E2E after measurement.
- 2026-10-19 **config-only for ~924** (no new OAI source): `configs/gnb/002.gnb.sa.e2e.band79.100mhz.273.fhi72.4x4.conf` — `force_256qam_off=0`, `dl_bler` 0.03/0.05, `ul_max_mcs=10` (original under `#` / `#if 0` comments). Env already `monolithic-e2e` / `MODE_IDX=3` / empty `DU_EXTRA_ARGS`. User builds/deploys; keep DL-opt binary; do not restart `oai-gnb-env`. OAI source (TDA/AMC) review later if measure misses 924.
- E2E-pre924 (2026-10-19 16:41, PID 1900029, RNTI cf00): Before 924 knobs. Qm 6 / MCS 26 / RI 4 / ~653 Mbit/s under ~1G offer. Clock clean.
- E2E-924a (2026-10-19 16:52, PID 2047602, RNTI c05d): 924 knobs live (`force_256qam_off=0`, BLER 0.03/0.05, `ul_max_mcs=10`). Under ~1G iperf: Qm **8**, RI 4, MCS **23**, CQI **13**, MAC **~763** / L1 **~789** Mbit/s (5 s), `dlsch_errors` 1, BLER ~1.5–3.1%. Clock clean. Gain vs pre924 ~+110 Mbit/s from 256QAM. Then limited by CQI 13 + climb gate.
- 2026-10-19 **Why not MCS 27 in E2E (early):** `dl_max_mcs=27` is only an allow-list. Operating MCS = min(BLER AMC, CQI ceiling, conf max). At 924a, CQI 13 capped below 27; BLER held ~MCS 23. Hist. best was MCS **24** @ CQI 15, never 27.
- 2026-10-19 **RF / CQI recovery (E2E-924b):** UE closer (~80 cm) → RSRP ~−51…−54, CQI **15**, MCS climbed to **25** (~878). CSI no longer the bottleneck.
- 2026-10-19 **`dl_max_mcs` hunt:** interim **25** → open **27** → AMC **26↔27** with BLER **0–7%** while CQI stayed 15 (20 s monitor: RSRP/CQI flat → swing is AMC edge, not CSI). Cap **`dl_max_mcs=26`** in project + live (`sudo` edit + `systemctl restart oai-du` @ 17:54).
- **E2E-924c** (2026-10-19 17:54–17:58, PID **2721721**, RNTI **3e76**): Settled. RSRP **−54**, CQI **15**, RI **4**, MCS **26**, NPRB 273, Qm 8, `dlsch_errors` **0**, BLER **~0.000–0.003**, retx ~0–0.3%. iperf **~880 Mbit/s**; MAC TX **~908** / LCID4 **~906** (14 s). Gap iperf↔MAC ~3% (RLC/PDCP/IP). vs hist. 924 MAC: −~16 Mbit/s with far lower retx — accept as stable E2E point unless RF supports clean MCS27.
- 2026-10-19 **Why `ul_max_mcs=10` not 16:** Comment in conf — hold UL so DL HARQ stays clean (prior UL MCS0 + DTX storm killed DL). Live UL at cap 10, SNR ~11 dB, BLER 0, NPRB 20 keepalive. Raising to 16 is optional for UL throughput only; does **not** move DL 880→924.
- 2026-10-19 **Theory max MCS26** (see Status §): DDSUU 400/s × (2×TBS_D + TBS_S). OAI live TypeA **2+12/2+8**, DMRS **36/24** → TBS **106587/69677** → **MAC ≈ 905** (matches ~908). **LGE ~950 with same RU + still 2+8** → gap is full-D **3 vs 2 DMRS** (2 DMRS → ~970 MAC), **not** mixed 1+9 / not RU pattern. Next lever: DMRS/CORESET on full D.
- **E2E-P1** (2026-10-19 18:25–18:28, PID 3010176, RNTI a2c6): `controlResourceSetZero=4`. Attach OK. Mixed TDA **1+9** (TBS 81975). 20 s: MAC **~967**, LCID4 **~965**, MCS26, CQI15, RSRP−54, BLER ~0.04, retx ~4%, PDSCH ~1150/s. Gain +~59 MAC vs P0 (~908). BLER higher than P0 — monitor before P3. **Best point so far this campaign.**
- **E2E-P2 FAIL** (2026-10-19 18:51, PID 3160153, RNTI aa4f): P1 + DMRS **pos0**. FH OK after VF MAC fix. 20 s: MAC **~609**, MCS 18–25 hunt, BLER up to **0.20**, retx **~31%**, err 6. CQI15/RSRP−54 flat → not RF. **Why worse:** pos0 strips extra DMRS on long TypeA @ RI4 → channel est. fails → NACK/AMC collapse outweighs TBS gain. Source: P2 gated **`#if 0`** (back to pos1). Do **not** retry pos0 without better RF.
- 2026-10-19 **P4 clarified:** `ul_max_mcs` 10→16 is **UL-only**; no DL gain. Skip unless measuring UL.
- 2026-10-19 **Toward 1G:** P1 MCS26 ≈ ceiling ~1000 MAC theory / ~965 live. Need **P5 then P3 (MCS27)** for ~1G iperf; no further free TDA/CORESET lever.
- 2026-10-19 **CSI note (21:33):** CQI wideband **stable 15**; instability was PMI/MCS/BLER and **RI=2**. Live had drifted to `force_256qam_off=1` / `dl_max_mcs=27` — restore P1 before new source work.
- 2026-10-19 **Source DL verdict:** No must-fix bug left for DL Mbps (AMC/CQI-gate/TDA/clock/DMRS already ported). Optional only: CSI hysteresis / milder AMC for stability. 1G = RF + MCS27, not a new TDA patch.
- Later E2E rows:

---

## 6. Commands (when measuring)

```bash
# what the DU loaded (P1 expect: force_256qam_off=0, dl_max_mcs=26, controlResourceSetZero=4)
grep -E 'nrofDownlinkSlots|nrofUplinkSlots|force_256qam_off|dl_max_mcs|ul_max_mcs|dl_bler|iq_width|initialDLBWPcontrolResourceSetZero' /etc/oai-gnb/conf/gnb.conf

# VF MAC (must match RU / DPDK_VF_MAC — else rx=0 after deploy)
ip link show ice1 | grep 'vf 0'

# binary identity
strings /opt/oai-gnb/bin/nr_softmodem | grep -E 'Branch:|Abrev'

# MAC / CSI sample
tail -n 40 /var/log/oai-gnb/nrMAC_stats.log
grep -aE 'mixed S PDSCH' /var/log/oai-gnb/du.log | tail -5
```

Restart `oai-du` after any `gnb.conf` edit. O-RU pattern-id must be 0 for DDSUU rows. After full deploy, verify VF MAC before blaming PHY.
