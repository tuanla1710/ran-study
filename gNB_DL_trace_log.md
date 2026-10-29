# DU max-throughput tracking

Living log for the n79 100 MHz O-DU (FHI 7.2, 4×4). Fill one row per run. Do not change more than one radio knob between two rows, or the comparison is useless.

Live file under test: `/etc/oai-gnb/conf/gnb.conf`  
Active profile (test case 1): `002.gnb.sa.tm.band79.100mhz.273.fhi72.4x4.dl.256qam.conf`  
`MODE_IDX=2`, `DEPLOY_PROFILE=monolithic-tm`, `DU_EXTRA_ARGS="-l 4"`, `dl_tx_eaxc_mask=15`  
E2E snapshot before this switch: `~/backup/gnb.conf.live.20261015-160626` and `~/backup/env.live.20261015-160633/`

Live as of 2026-10-15 18:54: E2E, `MODE_IDX=3`, no `--phy-test`. Same knobs as the 924 Mbit/s point. 256QAM on (`force_256qam_off=0`, `dl_max_mcs=27`, `dl_bler_target_lower=0.03`, `dl_bler_target_upper=0.05`). Dedicated PDSCH starts at symbol 1 (TDA 3/4/5). DMRS additional position pos1. CQI sets the MCS ceiling only. Cat A DL U-plane stays on the timing core. PID 2485288. Rerun bundle: `~/backup/e2e.900M.20261015-185722/` (gnb.conf, env, `nr_softmodem`). The 18:05 64QAM snapshot (681 Mbit/s) is `~/backup/gnb.conf.e2e.20261015-180550` and `~/backup/env.live.20261015-180550/`.

## Test case 1 status (2026-10-15 16:22)

DL phy-test, 100 MHz, 4 ports, DDSUU. DU is up on the package in `output/p5g-ran-gnb-26.0.1-x86_64`.

| Item | Value |
|---|---|
| Binary | `/opt/oai-gnb/bin/nr_softmodem`, hash `cff99d1c0` (2026-10-15 10:45). Replaces `e46fef98f` (2026-10-14) |
| Process | PID 970060, started 16:19:35. `--phy-test -l 4`, thread-pool `11-15,32-38` |
| MAC TX | **1345 Mbit/s** over a 3 s sample of `nrMAC_stats.log` (RNTI 1234) |
| PHY | MCS table 1, MCS 27, Qm 8 (256QAM), 273 PRB, `dlsch_errors = 0` |
| Rank | `current_RI = 1`. Command line asks for 4 layers; the stats are still one layer |
| UL | `ulsch_rounds = 0` (DL-only phy-test) |

CPU of `nr_softmodem` threads, 2 s sample. 100% means that core is full.

| Core | Thread | CPU |
|---|---|---|
| 5 | `fh_main_poll` | 100% |
| 6 | `fh_rx_bbdev` | 100% |
| 7 | `fh_cp_gen` | 100% |
| 8 | `L1_tx_thread` | 89% |
| 9 | `L1_rx_thread` | 16% |
| 10 | `ru_thread` | 9% |
| 11–15, 32–38 | `Tpool` (12 threads) | about 10% each |
| 39, 40, 41 | `fhtxcomp` | 4.5% each |

Core 4 (system) is idle. RRC, SCTP, GTP, and stats sit on cores 42–46, each under 1%. Fronthaul workers on cores 5, 6, and 7 are the saturated ones. L1 TX is close behind. MAC pool and BFP compress are not full. Rank 1 is the other cap on the 1345 Mbit/s figure: four layers are configured, one layer is what the stats report.

### du.log analysis (2026-10-15 16:32, PID 970060)

No assert and no crash after `xran_open`. The repeating errors are a slot-clock jump, not an O-RU pattern mismatch.

| Log line | Count since `xran_open` | What it is |
|---|---|---|
| `slot mismatch, received X, expected Y` | 17125 | XRAN slot is ahead of the RU thread |
| of which delta is exactly +3 slots | 17123 | Steady skip, not a random offset |
| `frame mismatch` | same jump, when +3 crosses a frame boundary | Second print of the same event |
| `PUCCH job ... is in the past` | still at the tail | PUCCH was queued for a slot the clock already skipped |
| `Cannot schedule SR. PRBs not available` | still at the tail | SR occasion missed after the jump |

Root cause: DL processing is short of real time, so the fronthaul RX queue is allowed to slip by 3 slots and then the DU jumps its clock forward.

`xran_fh_rx_read_slot()` in `radio/fhi_72/oaioran.c` blocks on the xRAN RX callback queue. `MAX_QUEUE_LENGTH_NO_JUMP` is 3. When the queue is longer than that, the function drops the older slots and returns the newest one. The RU thread in `nr-ru.c` has only done `slot++`, so `oran_fh_if4p5_south_in()` in `radio/fhi_72/oran_isolate.c` logs `Received Time doesn't correspond`. The comment on that threshold says the backlog is a steady ~15–20% real-time deficit under full-buffer DL, because the L1 TX thread is saturated. Raising the threshold from 3 to 8 was already tried: the queue grows to whatever the cap is. Three slots out of 20 slots per 10 ms frame is 15%, which matches this log (almost every sample is +3) and the CPU sample (cores 5–7 at 100%, L1 TX at 89%) while the test transmits 100 MHz, 4 ports, MCS 27, 273 PRB.

`LOG_W` "TTI processing delay detected, skipping" is not in `du.log` because `global_log_level` is `error`. The `LOG_E` slot mismatch is the visible form of that skip.

### Evidence on the AVX-512 image (2026-10-15 16:39, same PID 970060)

The process was not restarted between the 16:32 reading and this one. The binary string is `Branch: avx512 Abrev. Hash: cff99d1c0`, built `-march=skylake-avx512`. The slot jump is still accumulating on that image.

| Proof | Measurement |
|---|---|
| This is the AVX-512 DU | `/opt/oai-gnb/bin/nr_softmodem` → `Branch: avx512 Abrev. Hash: cff99d1c0 Date: Thu Oct 15 10:45:17 2026 +0900`. PID 970060 still `--phy-test -l 4` |
| Jump did not stop after boot | Slot-mismatch count since `xran_open`: 17125 at 16:32 → **24342** at 16:39. About 17 new mismatches per second |
| Jump size is the queue cap | **24339 / 24342** deltas are exactly **+3** slots. Two are +2, one is +23 |
| Saturated threads are fronthaul, not the AVX-512 L1 TX core | 2 s sample: core 5 `fh_main_poll` 99.8%, core 6 `fh_rx_bbdev` 100%, core 7 `fh_cp_gen` 100%, core 8 `L1_tx_thread` **89.3%** |
| MAC pool and BFP compress are idle by comparison | Cores 11–15 and 32–38: 9–10.5% each. Cores 39–41 `fhtxcomp`: 5% each |
| DL is on air while the clock jumps | 3 s MAC sample **1345 Mbit/s**. MCS table 1, MCS 27, Qm 8, 273 PRB, `dlsch_errors = 0`, `dlsch_rounds` 5.85e6 |
| Rank is 1, so this overload is not 4-layer L1 work | `CQI 0, RI 1`. L1 `current_RI 1`, `current_Qm 8`. Command line is `-l 4` |
| UL logs are not a live uplink | `ulsch_rounds = 0`, UL NPRB 0, RX bytes 0 |

AVX-512 is the instruction set of this binary. The three cores at 100% are the DPDK poll, U-plane RX, and C-plane generator. Those threads are outside the L1 TX AVX-512 path, and they are the ones that let the RX queue hit `MAX_QUEUE_LENGTH_NO_JUMP`.

### Control run: one eAxC (2026-10-15 16:45, PID 1237917)

`dl_tx_eaxc_mask` 15 → 1 and `DU_EXTRA_ARGS` `-l 4` → `-l 1`. MCS 27 and 273 PRB unchanged. DU restarted; `oai-gnb-env` was left up.

| Item | 4 eAxC (mask 15, `-l 4`) | 1 eAxC (mask 1, `-l 1`) |
|---|---|---|
| Steady slot mismatch | 24339 of 24342 were +3, about 17/s | **1 total**, at startup (`received 2.5, expected 0.18`, delta +27). **0 new** in a later 5 s window |
| MAC TX | 1345 Mbit/s | **343 Mbit/s** (about 1/4) |
| L1 TX core 8 | 89% | **37%** |
| Cores 5, 6, 7 | 100% | still about 100% (`fh_main_poll` 98%, `fh_rx_bbdev` 100%, `fh_cp_gen` 98%) |
| PHY | MCS 27, Qm 8, 273 PRB, RI 1, `dlsch_errors` 0 | same: MCS 27, Qm 8, 273 PRB, RI 1, errors 0 |

The +3 jump stops when only eAxC 0 is transmitted. MAC throughput scales by about 4, so mask 15 was sending four full 273-PRB streams. Core 5 staying near 100% does not by itself mean overload: `fh_main_poll` is a DPDK poll loop. The evidence that 4 eAxC was over budget is the mismatch rate falling from ~17/s to 0, together with L1 TX falling from 89% to 37%.

PUCCH "in the past" and `Cannot schedule SR` follow the jump. MAC had already queued those jobs for the skipped slots. They are not a separate O-RU fault. `current_RI = 1` is a separate cap on the 1345 Mbit/s MAC TX number.

### 4 eAxC restored, then the clock jump fixed (2026-10-15 17:06–17:32)

Mask put back to 15 and `DU_EXTRA_ARGS="-l 4"`. The +3 jump returned immediately. A later timing split showed the old "L1 TX is 15–20% over budget" note does not match this run.

| Step | PID | What changed | Result |
|---|---|---|---|
| 17:04, 1 eAxC | 1420605 | Skip CSI/SRS/SR/PUCCH when `phy_test` and `ulsch_slot_bitmap==0` | CSI flood gone. MAC **343 Mbit/s**, MCS 27, 273 PRB, errors 0 |
| 17:06, 4 eAxC | 1442399 | mask 15, `-l 4` | MAC **1348 Mbit/s**. **198** slot mismatches and **45** frame mismatches in ~18 s, almost all **+3** |
| 17:27 | 1633887 | `ru_thread` no longer waits on the L1 RX pipeline in DL-only phy-test | Log **clean**. MAC **1349 Mbit/s**, MCS 27, 273 PRB, `dlsch_errors` 0 |
| 17:32 | 1692092 | Same DL run, plus the E2E non-blocking path in the binary | Log **clean**. MAC **1350 Mbit/s**, same PHY |

Measured on PID 1442399 before the wait was removed:

| Thread | Core | CPU | Meaning |
|---|---|---|---|
| `fh_main_poll` / `fh_rx_bbdev` / `fh_cp_gen` | 5 / 6 / 7 | ~100% | Busy-poll. Also ~100% on 1 eAxC, which did not jump |
| `L1_tx_thread` | 8 | 88%, and it still sleeps ~11% | Not stuck at 100%. Not the thread holding the clock |
| `ru_thread` | 10 | ~8%, state mostly sleeping | Not compute-bound |
| MAC `Tpool` | 11–15, 32–38 | ~10% each | Idle relative to the clock |
| `fhtxcomp` | 39–41 | ~5% | BFP compress is not the limiter |

xRAN category A accepts only a timing core plus two workers (`xran_spawn_workers` returns failure above that). The idle MAC cores cannot be given to the fronthaul poll.

Clock path, measured with timestamps on the RX queue drain: `xran_fh_rx_read_slot()` itself took **14 µs**. The time until the next pull was **2000 µs**. That gap is `wait_free_rx_tti()` in `executables/nr-ru.c` (RX pipeline depth 4) on the mixed slot. Four callbacks queue during those 2 ms, and the next read jumps **+3**. About one jump every 5–6 frames.

Fixes now in the running binary:

- DL-only phy-test (`--phy-test` and `link_direction=dl`): do not call `wait_free_rx_tti`. Also skip CSI reporting, SRS, SR, and PUCCH, which were logging on a slot the UL bitmap had cleared.
- E2E and UL phy-test on FHI 7.2: still run uplink when the RX buffer is free. If that buffer is still in L1, drop that one UL slot (`skip_rx`) instead of blocking the fronthaul clock. RFsim still uses the old blocking wait.
- Category A with two workers builds DL U-plane on `fh_cp_gen` instead of inline in the symbol timer. That move alone did not stop the +3 jump; the RX wait did.

`current_RI = 1` is unchanged. The 1350 Mbit/s figure is still one reported rank with four eAxC streams on the air.

## 1. Cell under test

| Item | Value |
|---|---|
| Band / center | n79, 4.770 GHz |
| Bandwidth | 100 MHz, 273 PRB, SCS 30 kHz |
| MIMO | 4×4 (`maxMIMO_layers = 4`, `pusch_AntennaPorts = 4`) |
| TDD (restored) | **DDSUU**, 2.5 ms. O-RU pattern-id **0** |
| Slot map | `nrofDownlinkSlots = 2`, `nrofDownlinkSymbols = 10`, `nrofUplinkSlots = 2`, `nrofUplinkSymbols = 2` |
| Fronthaul IQ | `iq_width = 9` (data), `iq_width_prach = 16`. RU does not accept data 16-bit |
| Test case 1 | DL phy-test, 100 MHz, 4 ports. `tm_mode`: `link_direction=dl`, `dl_mcs=27`, `dl_bw=273`, `dl_bitmap=7`, `dl_tx_eaxc_mask=15` |
| DL MCS | `force_256qam_off = 0`, `dl_min_mcs = dl_max_mcs = 27` (256QAM). `independent_stream_mode = 1` |
| Layers | `--phy-test -l 4`, `uecap_file = uecap_ports4.xml` |
| Compress cores | `dl_compression_worker_cores = (39, 40, 41)` added from the live E2E map (template omitted them) |

DDSUU symbol share in a 5-slot period (70 symbols): DL 38/70 (54%), UL 30/70 (43%).  
DDDSU share: DL 52/70 (74%), UL 16/70 (23%). UL airtime on DDDSU is about half of DDSUU.

## 2. What to copy from the DU log for every run

During a 60 s iperf, sample one steady second of `du.log` (not the ramp). Record:

- DL: MCS, Qm, layers, PRB, HARQ retx, BLER, CQI
- UL: MCS, Qm, layers, PRB, SNR, `ulsch_DTX`, residual BLER
- `phy-test` lines only if `MODE_IDX=2`. E2E (`MODE_IDX=3`) uses AMC, not a fixed MCS
- Confirm the log TDD line is DDSUU and matches the O-RU pattern-id

Qm = 6 is 64QAM. Qm = 8 is 256QAM. A high MCS index on the 64QAM table is still 64QAM.

## 3. Run log

iperf3, 60 s, one direction at a time unless the row says bidirectional. Throughput is the receiver average, not the sender's first second.

| Run | Date | Pattern (gNB / RU) | Direction | iperf Mbps | MCS | Qm | Layers | PRB | Retx / DTX | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 2026-10-15 | DDDSU / (fill) | DL | 530 | | | | | | Pattern trial. Restored to DDSUU after this |
| 0 | 2026-10-15 | DDDSU / (fill) | UL | 68 | | | | | | One UL slot per 2.5 ms. `ul_max_mcs = 10` |
| TC1 | 2026-10-15 16:39 | DDSUU / 0 | DL phy-test | 1345 (MAC TX, not iperf) | 27 | 8 | RI 1 | 273 | errors 0 | mask 15, `-l 4`. +3 slot on 24339/24342 mismatches. L1 TX 89% |
| TC1b | 2026-10-15 16:45 | DDSUU / 0 | DL phy-test | 343 (MAC TX) | 27 | 8 | RI 1 | 273 | errors 0 | mask 1, `-l 1`, PID 1237917. Slot jump stopped. L1 TX 37% |
| TC1c | 2026-10-15 17:06 | DDSUU / 0 | DL phy-test | 1348 (MAC TX) | 27 | 8 | RI 1 | 273 | errors 0 | mask 15, `-l 4`, PID 1442399. +3 jump back (198 slot / 45 frame in ~18 s) |
| TC1d | 2026-10-15 17:27 | DDSUU / 0 | DL phy-test | 1349 (MAC TX) | 27 | 8 | RI 1 | 273 | errors 0 | PID 1633887. DL-only skips the RX wait. Log clean |
| TC1e | 2026-10-15 17:32 | DDSUU / 0 | DL phy-test | 1350 (MAC TX) | 27 | 8 | RI 1 | 273 | errors 0 | PID 1692092. E2E non-blocking UL drop is in the binary. This row is still DL-only; E2E not run |
| E2E-DL | 2026-10-15 18:04 | DDSUU / 0 | DL E2E | 700 sent, 681 received | 28 | 6 | RI 4 | 273 | errors 0 | PID 1946311, RNTI 27a9. MAC TX 702, LCID 4 700.5 over 3 s. CQI 15. 64QAM (`mcsTableIdx` 0) |
| E2E-256a | 2026-10-15 18:11 | DDSUU / 0 | DL E2E | 453 (MAC TX) | 18 | 6 | RI 4 | 273 | retx 27%, errors +0 in 3 s | PID 2037063, RNTI 94fb. `force_256qam_off=0`, `dl_max_mcs=27`. BLER filter 0.18. RLC `SDU buffer full` ~20k. CQI 13 |
| E2E-256b | 2026-10-15 18:19 | DDSUU / 0 | DL E2E | 709 (MAC TX) | 21 | 8 | RI 4 | 273 | retx 1.2%, errors 0 | PID 2126127, RNTI 0715. CQI seed no longer jumps MCS. BLER gate was 0.5% / 2%. CQI 14 |
| E2E-256c | 2026-10-15 18:22 | DDSUU / 0 | DL E2E | 665 (MAC TX) | 20 | 8 | RI 4 | 273 | retx 1.3% | Same PID 2126127. ~1180 PDSCH/s, carrier full. 0.5% climb gate held MCS at 20 while BLER was ~0.8% |
| E2E-256d | 2026-10-15 18:25 | DDSUU / 0 | DL E2E | 807 (MAC TX) | 25 | 8 | RI 4 | 273 | retx 2.5%, errors 0 | PID 2192836. Climb gate 2% / drop 5%. CQI 15. PDSCH still symbol 2+8 on the mixed slot, TBS 67600 |
| E2E-256e | 2026-10-15 18:31 | DDSUU / 0 | DL E2E | 924 (MAC TX, 8 s) | 24 | 8 | RI 4 | 273 | retx 3.6%, errors 0 | PID 2241074. Mixed slot TDA 5, symbol 1+9, TBS 79873 at MCS 25. CQI 15, BLER 0.042. Target 950 needs MCS 25; the 5% drop gate stops at 24. Backup of this config: `~/backup/e2e.900M.20261015-185722/` |
| E2E-256f | 2026-10-15 18:36 | DDSUU / 0 | DL E2E | 697 (MAC TX, 10 s) | 16 | 6 | RI 4 | 273 | retx 3.2%, errors 0 | PID 2307157, RNTI after reattach, RSRP −56, CQI 15, BLER 0.036. DMRS additional position pos0 (one symbol). MCS fell from 24 to 16. Reverted to pos1 |
| E2E-256g | 2026-10-15 18:38 | DDSUU / 0 | DL E2E | no sample | 0 | | | 0 | BLER 0.97, then release | PID 2322424. BLER gate widened to 5% / 8% to hold MCS 25. UE reestablished (cause Other Failure) and was released before a clean rate |
| E2E-256h | 2026-10-15 18:44 | DDSUU / 0 | DL E2E | 739 (MAC TX, 10 s) | 21 | 8 | RI 4 | 273 | retx 2.4%, errors 0 | PID 2369580, RNTI e8b1, RSRP −58, CQI 12, BLER 0.97%. Gate back to 3% / 5%. CQI 12 caps MCS at 21. ~1161 TB/s, carrier full |
| E2E-256i | 2026-10-15 18:48 | DDSUU / 0 | DL E2E | no sample | 8 then 0 | | RI 4 then 2 | 273 then 0 | UL BLER 0.58 at MCS 0 | PID 2422811. CQI ceiling removed so the outer loop could climb. First UE f066 was clean at MCS 8 (902/0 retx) then RLF. Later UEs stuck at MCS 0. Reverted the ceiling |
| E2E-256e-restore | 2026-10-15 18:54 | DDSUU / 0 | DL E2E | not remeasured | | | | | | PID 2485288. Live files put back to the E2E-256e knobs and binary. UE must attach again before the next sample |
| 1 | | DDSUU / 0 | UL | | | | | | | |
| 2 | | | | | | | | | | |
| 3 | | | | | | | | | | |
| 4 | | | | | | | | | | |
| 5 | | | | | | | | | | |

## 4. Scenario order

Run in this order. Stop when a row shows the limiter.

| Step | Change only this | Expect if the knob was the limiter |
|---|---|---|
| A | None. DDSUU on gNB and O-RU pattern-id 0. Repeat the 60 s DL and UL iperf | UL higher than 68 if airtime was the DDDSU limit. DL near or above 530 |
| B | Log Qm, layers, PRB on that run | Full cell is Qm 6 or 8, 4 layers, ~273 PRB. Anything less is the cap |
| C | `ul_max_mcs` from 10 toward 16 (64QAM table) or 27 (256QAM table), one step | UL Mbps moves. If it does not, AMC or SNR is holding MCS, not the cap |
| D | `force_256qam_off` 1 → 0, only after the UE log shows `pdsch-256QAM-FR1` | DL Qm becomes 8. If Qm stays 6, the UE did not advertise 256QAM |
| E | Rank. If layers stay at 1 or 2, check CSI-RS (`do_CSIRS`) and UE rank | 4 layers is required for the 4×4 budget. 2 layers is about half |
| F | Leave `iq_width = 9` | RU rejects data 16-bit. Do not change this to chase Mbps |

## 5. Result notes

Short cause under each run. One sentence.

- Run 0 DL:
- Run 0 UL:
- Test case 1 DL: 1345 Mbit/s at MCS 27 / Qm 8 / 273 PRB / RI 1. The +3 jump is `ru_thread` blocked ~2 ms in `wait_free_rx_tti` on the mixed slot, not the 14 µs fronthaul read. DL-only phy-test skips that wait (PID 1692092, 1350 Mbit/s, log clean). E2E drops one UL slot when the RX buffer is still busy instead of stopping the clock.
- E2E-DL: Offered 700 Mbit/s, receiver 681 Mbit/s. The DU matched the offer (MAC TX 702.1, bearer LCID 4 700.5, 3 s sample) at MCS 28, 64QAM, RI 4, 273 PRB, CQI 15, RSRP −68 dBm. That 3 s window added 3601 first-round TBs and 0 retransmissions, `dlsch_errors` 0. The 19 Mbit/s gap is after the DU. Attach is working on this binary (Msg4 ACK). No slot mismatch; one UL RX drop at startup (`2.17`). Moving DL U-plane build onto `fh_cp_gen` had broken RAR, so that path is back on the timing core.
- E2E-256: Turning 256QAM on with the 15% BLER dead zone left MCS 23 and a 27% first-HARQ NACK rate; MAC fell to 453 Mbit/s and RLC discarded SDUs. CQI was pushing the operating MCS up while the 0.9 filter still read under 0.15. After the outer loop follows the 100 ms window and CQI only sets the ceiling, retx fell to 1.2% and MAC was 709 Mbit/s at MCS 21, but a 0.5% climb gate then stuck MCS at 20 (665 Mbit/s) on a full carrier (~1180 PDSCH/s, 273 PRB, RI 4). Opening the gate to 2–5% reached MCS 25 and 807 Mbit/s. The remaining gap to the 950 target was an empty symbol: dedicated PDCCH is 1 symbol, while every PDSCH still started at symbol 2 for CORESET0. TDA 3/4/5 start at symbol 1. Mixed slot went from 2+8 (TBS 67600) to 1+9 (TBS 79873). Settled point is MCS 24, CQI 15, MAC 924 Mbit/s over 8 s, retx 3.6%, `dlsch_errors` 0, BLER 0.042. MCS 25 is about 5% more bits and would clear 950 only if retx stayed flat; at MCS 24 the window is already at the 5% drop gate, so the loop stays there. After that, pos0 DMRS (E2E-256f) dropped the same carrier to MCS 16 and 697 Mbit/s, so the second DMRS symbol stayed. Widening the gate to 5%/8% (E2E-256g) and removing the CQI ceiling (E2E-256i) both ended in reestablishment before a clean high-MCS sample; uplink at MCS 0 showed BLER 0.58 and one corrupt UL MAC PDU. With the 3%/5% gate restored, CQI 12 held MCS 21 at 739 Mbit/s (E2E-256h, retx 2.4%, errors 0). Live DU is back on the 924 Mbit/s files (PID 2485288). Rerun from `~/backup/e2e.900M.20261015-185722/`.
- Run 1 UL:

## 6. Commands

```bash
# confirm the file the DU actually loaded
grep -E 'nrofDownlinkSlots|nrofUplinkSlots|force_256qam_off|force_UL256qam_off|dl_max_mcs|ul_max_mcs|iq_width' /etc/oai-gnb/conf/gnb.conf

# DL iperf, 60 s (run on the UE; server on the N6/DNN side)
iperf3 -c <server> -B <ue_ip> -t 60 -i 5

# UL iperf
iperf3 -c <ue_ip> -B <server> -t 60 -i 5 -R
```

Restart the DU after any `gnb.conf` edit. The O-RU pattern-id must be 0 before the DDSUU rows in section 3.
