# AVX-512 DU porting log

Living log for **OAI DU / FHI 7.2 only**. Host ice, timing, Open5GS, RAN-TP stay in [porting_avx512.md](porting_avx512.md). CPU map: [cpu_core_isolcate_to_ubuntu_os_guide.md](cpu_core_isolcate_to_ubuntu_os_guide.md).

| Field | Value |
|-------|--------|
| Branch | `avx512` |
| Host | `oran` — HPE DL360 Gen11, 2× Xeon Gold 6530, HT off |
| Started | 13 Oct 2026 (first port) |
| Reset | 14 Oct 17:02 — restore to `master` AVX2 (`96e8e6ae9`) |
| This file | 14 Oct 2026 — DU-only log for the **second** port |
| Revision | 0.6 — 27 Oct: UL iperf ~954 is client 1 GbE, not DU |
| Source tag | `PORTING_AVX512_CPU /* HAVE LATUAN YYYY.MM.DD */` |
| First-port backup | `/home/oran/latuan/backup/gnb-modified-avx512-20261014-1630` |

Update this file after every DU build/conf/systemd change. Do not mix timing or 5GC events here. Every source/script edit on this port **must** use the tag in §0.

---

## 0. Tag rule — `PORTING_AVX512_CPU`

All second-port DU / ISA / CPU-map edits are marked so they can be grepped and reverted independently of host ice/timing.

**Canonical stamp**

```text
PORTING_AVX512_CPU /* HAVE LATUAN YYYY.MM.DD */
```

| Field | Value |
|-------|--------|
| Tag | `PORTING_AVX512_CPU` |
| Author | `LATUAN` |
| Date | `YYYY.MM.DD` (day of the edit, e.g. `2026.10.14`) |
| Find all | `grep -RIn PORTING_AVX512_CPU scripts/gnb configs/gnb configs/systemd sources/openairinterface5g-v26.w14 sources/o-du-phy-oran_f_release_v1.9` |

Do **not** reuse `__GL_OAI_DU_PORTING__` / `__PORTING_TM_MODE__` for this Intel CPU port. Ice/GNSS is not tagged here.

**C / C++ / Makefile** (keep original under `#else` when replacing)

```c
#if 1 /* LATUAN 2026.10.14 PORTING_AVX512_CPU */
    /* new AVX-512 / DL360 CPU path */
#else /* HAVE LATUAN PORTING_AVX512_CPU */
    /* original AVX2 / AMD path */
#endif /* HAVE LATUAN PORTING_AVX512_CPU */
```

One-line add:

```c
/* PORTING_AVX512_CPU */ /* HAVE LATUAN 2026.10.14 */
```

**Shell** (`gnb_manager.sh`, `xran_manager.sh`, `dpdk_manager.sh`, `deploy.sh`, `oai_gnb_env.sh`)

```bash
# PORTING_AVX512_CPU /* HAVE LATUAN 2026.10.14 */
export CFLAGS="-O3 -march=skylake-avx512 -mtune=skylake-avx512 ..."
# endif PORTING_AVX512_CPU /* HAVE LATUAN 2026.10.14 */
```

**Conf / systemd** (key that changed)

```text
# PORTING_AVX512_CPU /* HAVE LATUAN 2026.10.14 */
  dpdk_devices = ("0000:11:09.0");
# endif PORTING_AVX512_CPU /* HAVE LATUAN 2026.10.14 */
```

When a tagged block is committed, add one line under §5 Event log and §8 Notes: date, files, grep hit count.

---

## 1. Status

| Item | Now (git tree / host `oran`) | Target (second port) |
|------|------------------------------|----------------------|
| ISA | **Tagged AVX-512** (`#if 1 PORTING_AVX512_CPU`; AVX2 in `#if 0`) | same (`-march=skylake-avx512`, `-DAVX512=ON`, `XRAN_ISA=avx512`, DPDK `-Dmachine=skylake-avx512`) |
| `dpdk_devices` | **40/100 MHz tagged `0000:11:09.0`** (31 files). 20/50/60/80 + `du.conf` still `81:09.0` | VF `0000:11:09.0` (ice1, vfio-pci, NUMA0) |
| `ru_addr` | **100/40 MHz tagged `F0:58`**. Other BW / `du.conf` still `F1:06`; SOC `003` keeps SOC MAC | Live `/etc/oai-gnb/conf/gnb.conf` **is `F0:58`** (100 MHz 4×4) |
| NUMA | env **`DU_NUMA_NODE=0`** / `DPDK_NUMA_NODE=0` | 0 (E810 node0 = `0-15,32-47`) |
| FHI cores | **40/100 MHz:** system 4 / io 5 / workers 6–7 / L1 8–9 / RU 10. Other BW still AMD 16–22 | same as 40/100 |
| `THREAD_POOL` | env + `deploy.sh` fallback **`11–15,32–38`** | same |
| `oai-du.service` | **keep** `chrt -f 99` + **`CPUAffinity=4-15,32-41`** + DPDK `LD_LIBRARY_PATH`; `KillMode=control-group`; `TimeoutStopSec=10` | FIFO 99 off CPU 0–1; L1/xRAN FIFO 97 via `threadCreate` |
| Clean AVX-512 rebuild | gNB package rebuilt/installed on `oran` 15 Oct | `objdump` `zmm` still optional |
| Loaded DU start | **`oai-du` active** — FHI `on_time`; live PCI `11:09.0` | UE attach / slot overrun still lab follow-up |
| E2E UL iperf 1G | Client `192.168.1.64` → CPE `192.168.225.1` is **RTL8153 1000 Mb/s**. UDP `-b 1000M` reports **~954 Mbps** (1 GbE payload). Not a DU/TDD/MCS clip | >1 Gbit/s needs 2.5G/10G UE LAN |

Ice GNSS/DDP is **host**, not DU source. Do not treat `ice_manager.sh` as part of `build-gnb`.

---

## 2. In / out of scope

**In:** OAI `nr_softmodem`, xRAN FHI, DPDK for FHI, `configs/gnb/*`, `oai-du` / `oai-gnb-env` / CU units, `scripts/gnb/{gnb,xran,dpdk}_manager.sh`, `deploy.sh`, `oai_gnb_env.sh`.

**Out:** ice OOT/GNSS/DDP, timing stack, Open5GS, RAN-TP, VPP, isolcpus GRUB (already on host).

---

## 3. Files to change (second port)

### 3.1 Build (clean-build on DL360)

| File | First port (reverted) |
|------|------------------------|
| `scripts/gnb/dpdk_manager.sh` | meson `-Dmachine=skylake-avx512` |
| `scripts/gnb/xran_manager.sh` | `XRAN_ISA=avx512`; drop `XRAN_PORTABLE_CPU` |
| `scripts/gnb/gnb_manager.sh` | `-march=skylake-avx512`; drop `--noavx512`; `-DAVX512=ON` |
| `sources/o-du-phy-oran_f_release_v1.9/fhi_lib/lib/Makefile` | skylake-avx512 + AVX-512 BFP objects |
| `…/fhi_lib/lib/api/xran_compression.hpp` | `BFP*Avx512` APIs |
| `…/fhi_lib/lib/src/xran_compression.cpp` | dispatch AVX-512, not scalar `BFP*Ref` |
| `sources/openairinterface5g-v26.w14/radio/fhi_72/CMakeLists.txt` | skylake-avx512 |
| `…/radio/fhi_72/mplane/CMakeLists.txt` | skylake-avx512 |
| `…/common/utils/gl_ul_statistics.c` | **Not edited.** Still `thread_top_init()`; boot gated by `GL_UL_STATISTICS_DISABLE=1` |

Order: `dpdk_manager.sh clean-build` → `xran_manager.sh clean-build` → `gnb_manager.sh build-gnb`. Binaries must not run on AMD (`SIGILL`).

### 3.2 Run (no rebuild)

| File | First port (reverted) |
|------|------------------------|
| `configs/gnb/*{40mhz,100mhz}*` | **Done 15 Oct:** PCI `11:09.0`, RU `F0:58`, FHI/L1/RU cores §4. 20/50/60/80 + `du.conf` **not** remapped |
| `configs/gnb/env/oai_gnb_fhi72_env.conf` | **Done:** NUMA 0; `DU_CPU_CORE=4–15,32–45`; `THREAD_POOL=11–15,32–38`; `GL_UL_STATISTICS_DISABLE=1` |
| `configs/systemd/oai-du.service` | **Done, keep `chrt -f 99`** (not dropped). `CPUAffinity=4-15,32-41`; `KillMode=control-group`; `TimeoutStopSec=10`; `LD_LIBRARY_PATH` + DPDK |
| `oai-cucp.service` / `oai-cuup.service` / `oai-gnb-env.service` | **Done:** CU `LD_LIBRARY_PATH` DPDK; env systemd **PATH** includes `/opt/dpdk-22.11.11/bin` |
| `scripts/gnb/env/oai_gnb_env.sh` | **Done:** PATH `dpdk-devbind.py`. VF bind already `vfio-pci`. **No** auto-rewrite of `dpdk_devices` in conf |
| `scripts/gnb/deploy.sh` | **Done:** THREAD_POOL fallback `11–15,32–38`. IOMMU already on host. **No** `dpdk_devices` sync |

Host already: `intel_iommu=on iommu=pt`, vfio VF `0000:11:09.0`, IOVA VA. Other-BW templates still say `81:09.0` until remapped.

---

## 4. DU CPU target (node 0)

From the isolation guide. Do not reuse AMD 16–31.

| Cores | Role |
|-------|------|
| 0–1 | Housekeeping — **DU must not run here** |
| 2–3 | Timing (not DU) |
| 4 / 5 / 6–7 | FHI system / io / xRAN workers |
| 8 / 9 / 10 | L1 TX / L1 RX / RU |
| 11–15, 32–38 | `THREAD_POOL` |
| 16–31 | Open5GS / UPF — **not DU** |
| 39–41 | DL BFP compress |
| 43–45 | CU-UP / CU-CP (split only) |

`oai-du` cgroup: `CPUAffinity=4-15,32-41` (spare 42–47 free).

**Hang (B20261014-14).** First start of 100 MHz 4×4 froze SSH: process-wide `chrt -f 99` + empty affinity put FIFO 99 on CPU 0–1. Second port **keeps** `chrt -f 99` and adds `CPUAffinity=4-15,32-41` so FIFO 99 stays off housekeepers 0–1 / 16–23. Live unit has that affinity (15 Oct).

---

## 5. Event log

| Time (JST) | Event |
|------------|--------|
| 13 Oct | Branch `avx512` from `master` @ `c80667a10`. First ISA port: OAI/xRAN/DPDK → skylake-avx512 |
| 14 Oct morning | Runtime: VF `0000:11:09.0`, IOMMU VA, PATH/`LD_LIBRARY_PATH` DPDK. DU FHI `on_time` then **host hang** (FIFO 99 on CPU 0–1) |
| 14 Oct afternoon | Working tree: drop process `chrt`; `CPUAffinity=4-15,32-41`; UL-stat disable. **Not applied live.** Operator paused DU start |
| ~16:30 | Backup 84 DU/gNB files → `/home/oran/latuan/backup/gnb-modified-avx512-20261014-1630` |
| 17:02 | **Restore** build+run DU files to `master` AVX2. Commit `96e8e6ae9`. Ice **kept**. Pushed `origin/avx512` |
| 17:08 | Deleted unused `configs/systemd/dropins-host/` |
| ~17:17 | Isolation guide committed (`b661261e9`) — DL360 64-core map. gNB conf still AMD until this second port |
| 17:18 | This log created |
| 17:25 | Tag rule: every DU/ISA/CPU edit uses `PORTING_AVX512_CPU /* HAVE LATUAN YYYY.MM.DD */` (§0). `gnb_manager.sh` restored to pre-`e5b6820ea` (`6ab43bc43` / `b03e87334`) |
| 17:27 | Second-port **build ISA** tagged: `gnb_manager.sh`, `xran_manager.sh`, `dpdk_manager.sh`, xRAN `Makefile` + BFP dispatch, FHI CMake. AVX2 kept in `#else`. No `sudo dpdk install` / no `ldpc_aal` (kept from restore). Runtime conf **not** done |
| 15 Oct | `ru_addr` → `8C:1F:64:41:F0:58` on **100 MHz + 40 MHz** templates only (30 files, tagged). Skip 20/50/60/80, `du.conf`, SOC `003` MAC. 40 MHz e2e old was `F0:08` |
| 15 Oct | FHI/L1/RU cores + `thread_pool` remapped on **40/100 MHz only** (AMD 16–31 → DL360 §4). Env NUMA0, `THREAD_POOL=11–15,32–38`, `GL_UL_STATISTICS_DISABLE=1` |
| 15 Oct | `dpdk_devices` → `0000:11:09.0` on **31** 40/100 MHz files (incl. SOC `003` PCI). 20/50/60/80 + `du.conf` still `81:09.0` |
| 15 Oct | systemd: keep `chrt -f 99`; `CPUAffinity=4-15,32-41`; DPDK `LD_LIBRARY_PATH`; env PATH `/opt/dpdk-22.11.11/bin` (`dpdk-devbind.py`). `deploy.sh` THREAD_POOL fallback remapped |
| 15 Oct | Bring-up: `librte_timer.so.23` miss (fixed by `LD_LIBRARY_PATH`); then EAL miss `81:09.0` (fixed by live `11:09.0`). `oai-du` **active**, FHI `on_time` |
| 15 Oct | Unused `configs/systemd/dropins-host/` moved out of tree → `/home/oran/latuan/open5g-ran-core-backup/dropins-host/` (affinity already in unit) |
| 26 Oct | E2E 100 MHz 4×4: iperf DL stuck ~367 (TCP and UDP). N6 `ogstun` ~1 Gbit/s; MAC/LCID4 ~740–800; FHI `on_time` ~3.74 Gbit/s. `ice1` / DPDK VF: no QoS/shaper. Open5GS AMBR 1 Gbit/s |
| 26 Oct | Channel: afternoon RSRP −66 CQI 13 MCS 21–22; evening CQI 15 MCS 25 MAC ~800 but printed RSRP −91…−96 (UCI/PUCCH DTX — not a real −40 dB drop). MCS 27 BLER >5% @ RI4 — keep `dl_max_mcs=26` |
| 26 Oct | RLC trial ms80/ms40/ms5/kB2000 did not move 367; **reverted** to 2026-07-15 set (ms45/ms15/ms15/kB500). `ngap_log_level` stays **debug** |
| 26 Oct | `002` e2e: `tx_amp_backoff_dB` **14 → 17** (measured better than 16 vs O-RU 20±1). Live `gnb.conf` already 17; copy 002 if live RLC still on the trial set |
| 27 Oct | UL iperf on CLIENT `192.168.1.64`: `iperf3 -c 10.45.0.1 -p 5204 -u -b 1000M` (no `-R`) → **~954 Mbps**. SSH check: send NIC `enx2c3068009d6c` is USB RTL8153 **Gigabit** @ 1000 Mb/s MTU 1500. 954 = 1 GbE goodput, not radio |

---

## 6. Second-port checklist

Tick and date in this table as you go.

| # | Work | Done |
|---|------|------|
| 1 | ISA flags: DPDK meson, xRAN `avx512` + BFP, OAI `-DAVX512=ON` | **2026.10.14** tagged `#if 1 PORTING_AVX512_CPU` / `#if 0` original |
| 2 | `clean-build` DPDK → xRAN → OAI on `oran`; `objdump` for `zmm` | **gNB rebuilt/installed 15 Oct.** `objdump zmm` still open |
| 3 | Templates: PCI `11:09.0`, RU `F0:58`, FHI/L1 cores §4 | **2026.10.15 40/100 MHz only** (PCI 31 files; cores + RU MAC). Other BW / `du.conf` still AMD |
| 4 | Env: NUMA 0, `DU_CPU_CORE` / `THREAD_POOL` §4, `GL_UL_STATISTICS_DISABLE=1` | **2026.10.15** |
| 5 | `oai-du.service`: **keep** `chrt -f 99`; `CPUAffinity=4-15,32-41`; DPDK `LD_LIBRARY_PATH` | **2026.10.15** (plan changed: do not drop `chrt`) |
| 6 | `oai_gnb_env.sh` / `deploy.sh`: PATH + THREAD_POOL. VF auto-sync of `dpdk_devices` **not** added | PATH **2026.10.15**. IOMMU already on. Sync leftover |
| 7 | Live `/etc/oai-gnb/conf/gnb.conf` RU MAC `F0:58` + PCI `11:09.0` | **2026.10.15** (100 MHz 4×4 profile) |
| 8 | Start `oai-gnb-env` + `oai-du`; FIFO 99 off CPU 0/1 | **`oai-du` active 15 Oct**; `CPUAffinity=4-15,32-41` live |
| 9 | FHI eCPRI to O-RU; no `SIGILL`; record slot overrun | FHI **`on_time` 15 Oct**. UE Msg3 / overrun still lab |

Reference only: backup `INFO.md` + `vs-master.diff`. Do not copy blindly — tree and host moved on.

---

## 7. Defects (DU)

| ID | Symptom | Status |
|----|---------|--------|
| B20261014-5 | vfio `EINVAL` / IOVA PA vs VA | Host IOMMU **fixed**. Live VF `11:09.0` vfio-pci, EAL VA. Script auto-sync of `dpdk_devices` still not in `deploy.sh` |
| B20261014-6 | AMD PCI `81:09.0` / missing `librte` / `dpdk-devbind.py` | **Mitigated 15 Oct:** 40/100 templates `11:09.0`; unit `LD_LIBRARY_PATH` DPDK; env PATH `dpdk-devbind.py`. Other BW still `81:09.0` |
| B20261014-7 | Live RU MAC `F1:06` | **Live 100 MHz `gnb.conf` is `F0:58`.** Other BW templates still `F1:06` |
| B20261014-14 | Host hang on DU init | **Mitigated 15 Oct:** keep `chrt -f 99` + `CPUAffinity=4-15,32-41`. DU running |
| B20261014-15 | Restore first port to AVX2 | **Done** `96e8e6ae9` (then second port re-tagged ISA) |
| B20261015-1 | `liboai_transpro` / `librte_timer.so.23` | **Fixed** DPDK dir on `LD_LIBRARY_PATH` (`oai-du` / cucp / cuup) |
| B20261015-2 | EAL `Cannot find device (0000:81:09.0)` | **Fixed** live + 40/100 templates → `0000:11:09.0` |
| B20261027-1 | UL iperf `-b 1G` / `1000M` shows ~954 Mbps; operator expected 1000 | **Not DU.** Client `192.168.1.64` UE LAN is RTL8153 1 GbE (`enx2c3068009d6c` → `192.168.225.1`). Payload ceiling `1e9×1472/1538 ≈ 957 Mbps`. Raising MCS/TDD/`-b` will not pass 954 until 2.5G/10G UE NIC+CPE |

---

## 8. Notes (append below)

- 2026-10-14 17:27  ISA build tagged `PORTING_AVX512_CPU /* HAVE LATUAN 2026.10.14 */`. Files: `scripts/gnb/{gnb,xran,dpdk}_manager.sh`, `sources/o-du-phy-oran_f_release_v1.9/fhi_lib/lib/{Makefile,api/xran_compression.hpp,src/xran_compression.cpp}`, `radio/fhi_72/{CMakeLists.txt,mplane/CMakeLists.txt}`.
- 2026-10-15  RU MAC `8C:1F:64:41:F0:58` on 16× 100 MHz (`002`) + 14× 40 MHz (`004`). Tag `PORTING_AVX512_CPU /* HAVE LATUAN 2026.10.15 */`. Not touched: 20/50/60/80 MHz, `du.conf`, SOC `003` MAC.
- 2026-10-15  Cores + PCI on 40/100 MHz (`002`/`004` + SOC `003` PCI). Env NUMA0 / pool `11-15,32-38` / `GL_UL_STATISTICS_DISABLE=1`. Units: keep `chrt`, `CPUAffinity`, DPDK `LD_LIBRARY_PATH`, PATH `dpdk-devbind.py`. `gl_ul_statistics.c` still calls `thread_top_init()` — gated by env disable. Grep `PORTING_AVX512_CPU`: **46 files**.
- 2026-10-15  Live: `oai-gnb-env` + `oai-du` active; `gnb.conf` 100 MHz 4×4; VF `0000:11:09.0` vfio-pci; FHI `on_time`. Local `du.sh` bring-up helper untracked. Drop-in backup: `/home/oran/latuan/open5g-ran-core-backup/dropins-host/`.
- 2026-10-26  E2E DL: 367 is not ice1/DPDK/AMBR/RLC. Radio MAC ~750–800 (CQI 13 or MCS 25). 950 needs RSRP ~−54 / CQI 15 / MCS 26 stable. `tx_amp_backoff_dB=17` in `configs/gnb/002.gnb.sa.e2e.band79.100mhz.273.fhi72.4x4.conf`.
- 2026-10-27  E2E UL ~954 Mbps is the **UE-PC 1 GbE payload ceiling**, not AVX-512 / TDD / MCS. SSH `oran@192.168.1.64`:
  - `enx2c3068009d6c` `192.168.225.127/24` **1000 Mb/s** USB RTL8153 (`0bda:8153`, fw `rtl8153b-2`) → CPE `192.168.225.1`. Route `10.45.0.1 via 192.168.225.1`. Ping N6 ~14 ms.
  - `enx588694f6b52f` `192.168.1.64/24` **1000 Mb/s** RTL8153 — lab LAN / SSH only.
  - Onboard `enp3s0` RTL8168 **down** (no cable); also 1G-only.
  - Live sender: `iperf3 -c 10.45.0.1 -p 5204 -t 3600 -i 1 -b 1000M -u` (UL, no `-R`). iperf 3.20.
  - Wire 1.000 Gbit/s; 1500 MTU frame is 1538 B on the wire (8 pre+SFD + 14 Eth + 20 IP + 8 UDP + **1472 payload** + 4 FCS + 12 IFG). UDP goodput `1e9 × 1472 / 1538 ≈ 957 Mbps`; TCP ~941–954. iperf reports payload, so 954 is a full 1G NIC.
  - Do not retune DU for this number. To go past 954: 2.5G/10G NIC + matching CPE LAN. Jumbo on RTL8153 only adds tens of Mbps. Compare `MAC RX` vs iperf on the same window ([gnb_ul_e2e_throughput_checklist.md](gnb_ul_e2e_throughput_checklist.md)).
