# LATUAN ACC100 LDPC offload — design

**Author:** LATUAN  
**Date:** 2026.10.20  
**Revised:** 2026.10.20 — deploy runbook, plus install/uninstall hazards for ACC init (analysis only, no code change)  
**Status:** design only. Do not implement from this file until asked.  
**Tag:** `LATUAN_ACC100_LDPC`

This design turns on the LDPC path already in this tree (`ldpc_aal` + Intel ACC100 + FHI 7.2). It does not add a codec, does not change 256QAM, and does not implement 1024QAM.

Stamp for every future edit that belongs to this work:

```text
LATUAN_ACC100_LDPC /* LATUAN YYYY.MM.DD */
```

Do not reuse `PORTING_AVX512_CPU`, `PORTING_AVX512_DL_OPTIMIZE`, `__PORTING_TM_MODE__`, `__PORTING_E2E__`, or `LATUAN_1024QAM` for this work.

```bash
grep -RIn LATUAN_ACC100_LDPC sources/openairinterface5g-v26.w14 configs/gnb scripts/gnb docs/
```

---

## 1. Goal

Move LDPC encode/decode from the CPU library to the ACC100 VF, on the live n79 100 MHz 4×4 cell, without touching the E810 fronthaul and with a rollback that fits in one DU restart.

ACC100 does not run FFT, channel estimation, MIMO, modulation, resource mapping, or FHI. Those stay on the CPU cores already pinned in `oai_gnb_fhi72_env.conf`.

The offload is **off** unless the running conf sets `loader.ldpc.shlibversion = "_aal"`. Every other profile keeps CPU LDPC.

---

## 2. What is already true on this host

| Piece | Live value | Do not change for this upgrade |
|---|---|---|
| DPDK | `/opt/dpdk-22.11.11` | FHI is linked here. No second DPDK, no `dpdk-hugepages.py`. |
| Hugepages | `DPDK_HUGEPAGE_SIZE=2M`, `NR_HUGEPAGES=8192` on NUMA 0 | About 16 GiB. Resetting the pool drops the DU. |
| Fronthaul PF | `DPDK_PF_IF=ice1`, one VF | `oai-gnb-env.service` owns this. |
| FHI VF in conf | `fhi_72.dpdk_devices = ("0000:11:09.0")` | Not the ACC address. |
| FHI cores | system 4, io 5, workers 6–7, L1 TX 8, L1 RX 9, RU 10 | ACC must not be given any of these. |
| Other RAN cores | thread pool 11–15,32–38; DL compress 39–41 | Same. Core 42 is the only spare on this map. |
| DU unit | `oai-du.service` | `Requires=oai-gnb-env.service`. Binary `/opt/oai-gnb/bin/nr_softmodem`. |
| Running conf | `/etc/oai-gnb/conf/gnb.conf` | A copy. Editing `configs/gnb/` does nothing until this file is replaced. |
| Env | `/etc/oai-gnb/conf/env/oai_gnb_fhi72_env.conf` | `MODE_IDX=3` is E2E. `MODE_IDX=2` is phy-test. |
| Log | `/var/log/oai-gnb` (`WorkingDirectory` of the unit) | Grep this directory, not the build tree. |
| LDPC today | CPU library, `max_ldpc_iterations = 15` | Leave 15 for the first ACC run. |
| `skip_rx_if_busy` | `1` on the 100 MHz 4×4 E2E and TM DL confs | Leave it. ACC does not replace it. |

`scripts/gnb/gnb_manager.sh` `build-gnb` does **not** pass `--build-lib ldpc_aal`, so `libldpc_aal.so` is not in the image yet. The loader and the FHI hook already know what to do once that library and the conf key exist:

- `shlibversion = "_aal"` loads `libldpc_aal.so`.
- Any other value, or no key, loads the CPU library.
- On FHI, `radio/fhi_72/oran-config.c` reads the same key. `_aal` and `is_t2 = 0` hand the ACC VF to xRAN (`XRAN_BBDEV_MODE_HW_ON`). Otherwise BBDEV stays unused.
- `nrLDPC_coding_init()` then probes that VF. If the probe works, it does **not** call `rte_eal_init` again.

OAI uses the ACC100 **VF** (`8086:0d5d`), never the PF (`8086:0d5c`). `pf_bb_config` in VFIO mode is a daemon. If it dies, the VF is dead until the daemon and the DU are both started again.

---

## 3. Decisions

| ID | Decision |
|---|---|
| D1 | One VF, 5G only: `sources/pf-bb-config/acc100/acc100_config_1vf_5g.cfg`. 4G queue groups stay 0. 5G UL and 5G DL: 4 groups × 16 queues. |
| D2 | Opt-in. CPU LDPC stays the default for every conf that has no `loader.ldpc` block. |
| D3 | Write the block only into the two 100 MHz 4×4 files in section 7. Not into UL TM. Not into other bandwidths. |
| D4 | On FHI, do not set `dpdk_core_list`. xRAN already initialized EAL on cores 4–7. A second EAL init means the VF was not published. Fix the conf. Do not add a core list to hide that. |
| D5 | `is_t2 = 0`. |
| D6 | ACC BDF never goes into `fhi_72.dpdk_devices`. |
| D7 | First bring-up uses the stock AAL setup: one encode queue and one decode queue (`active_dev.nb_queues = 2`), callers under `encode_mutex` / `decode_mutex`. Do not retune the ACC queue map in the same step. |
| D8 | Keep `max_ldpc_iterations = 15` and `dl_bler` 0.03 / 0.05. The OAI note (200 iterations, BLER 0.15 / 0.35) is a later, separate test, and only if BLER rises after a clean BBDEV start. |
| D9 | Leave `skip_rx_if_busy`. |
| D10 | Maintenance window stops `oai-du` only. Never `deploy.sh stop`, never `systemctl restart oai-gnb-env`. Those tear down the E810 VF. |
| D11 | `pf_bb_config` becomes its own systemd unit so a reboot does not silently fall back to a dead VF. It must not `Want` or `Require` `oai-gnb-env`. |
| D12 | One change per DU start. Card test, binary swap, and conf swap may share one window. An iteration change or a queue-map change gets its own window. |
| D13 | Do not turn ACC on by `deploy.sh install` or `uninstall`. Those commands stop `oai-gnb-env`, and that unit's `ExecStop` shrinks hugepages to 0 and can sit forever while a dying DU still holds them. They also `SIGKILL` `nr_softmodem` without restarting `pf_bb_config`, which leaves the ACC VF wedged for the next init. |
| D14 | `pf_bb_config` is not part of the gNB cgroup. `stop` / `install` must not kill it, and must not `rmmod vfio-pci`. Its command line must not contain the substring `/etc/oai-gnb/conf/gnb.conf`, or `pkill -f` in `stop_stack` kills the daemon. |
| D15 | UUID and the ACC cfg live outside the tree that `uninstall` deletes (`/etc/oai-gnb`) and outside the tree that `install` overwrites (`cp -a` onto `/etc/oai-gnb`). Use `/var/lib/oai-acc100/`. |
| D16 | A gNB image whose packaged `gnb.conf` sets `shlibversion = "_aal"` must not be installed until G0 has passed and `pf_bb_config` is up. An image whose conf has no `_aal` key silently returns the cell to CPU LDPC. Neither outcome may be a surprise at `deploy.sh start`. |

---

## 4. What “stable” means before this becomes the live path

Do not leave the ACC conf in place overnight unless every gate below passed.

| Gate | Mode | Pass | Fail action |
|---|---|---|---|
| G0 | card, DU stopped | `dpdk-test-bbdev` validation exits 0 | Start the **old** DU immediately. Do not install the new binary. |
| G1 | first 60 s of `oai-du` | Log shows `libldpc_aal.so`, `skipping EAL initialization`, `bbdev <VF> found`, encode queue and decode queue. No assert. | Rollback, section 9. |
| G2 | TM DL, 10 min | Cell stays up. No new +3 slot jump versus the current TM DL run. MAC TX recorded next to the current MCS 27 / 273 PRB number. | Rollback if the rate drops by more than 5%, or if the clock jumps. |
| G3 | E2E attach | UE on, PDSCH and PUSCH both flow, `max_ldpc_iterations` still 15. | Rollback on attach failure or a BBDEV assert. |
| G4 | E2E iperf, ≥ 60 s | DL iperf at MCS 26 stays within 5% of the current live result (950 Mbit/s). `skip_rx` may fall. It must not be removed. | Rollback. Do not “fix” it by raising iterations in the same run. |

A pass of G2 with a fail of G4 means encode offload is usable and decode offload is not. The E2E conf goes back to CPU LDPC. The TM DL conf can stay on ACC only if G2 passed and someone explicitly keeps it.

---

## 5. Fast path

Build while the cell is up. The DU stop is only for the card smoke test and the file swap. If the smoke test fails, the old DU comes back and the cell is unchanged.

```text
[cell up]  build libldpc_aal.so + new nr_softmodem
[cell up]  bind ACC PF, start pf_bb_config, create 1 VF
           (does not touch ice1, hugepages, or oai-gnb-env)
[stop oai-du only]
           backup /opt/oai-gnb/bin/nr_softmodem and /etc/oai-gnb/conf/gnb.conf
           dpdk-test-bbdev          — fail: start old DU, stop
           install .so + binary
           install the two conf blocks into the *running* gnb.conf
[start oai-du]
           60 s log gate             — fail: rollback, start old DU
           then G2 (TM) and G3/G4 (E2E) in separate windows
```

`dpdk-test-bbdev` is inside the window because it allocates hugepages. Running it under a live DU can steal the pool FHI is using.

Do not use `deploy.sh install`, `install-only`, `uninstall`, `stop`, or `restart` for this upgrade. Section 5A is why. The fast path stops and starts `oai-du` only, and copies `nr_softmodem` plus `libldpc_aal.so` by hand.

---

## 5A. `deploy.sh` install / uninstall versus ACC init

Analysis of the scripts as they are today. No test was run. No script was changed. This section is the constraint on any later implementation.

`deploy.sh install` and `uninstall` do not know about ACC100. They were written for the E810 VF on `ice1` only. Once a conf sets `_aal`, the same commands can hang the upgrade or make the next DU die inside `nrLDPC_coding_init`.

### What install and uninstall actually run

`install_target` (`scripts/gnb/deploy.sh`) does this, in order:

1. One `systemctl stop` of `oai-gnb.target`, `oai-du`, `oai-cuup`, `oai-cucp`, and `oai-gnb-env`.
2. `cp -a` of the image's `opt/oai-gnb` onto `/opt/oai-gnb`, and of `etc/oai-gnb` onto `/etc/oai-gnb`.
3. Replace the four systemd units from the image, then `daemon-reload`.
4. It does **not** start the stack. The next `deploy.sh start` starts `oai-gnb-env` and `oai-du` together.

`oai-gnb-env.service` is `Type=oneshot`, `RemainAfterExit=yes`. `ExecStart` is `oai_gnb_env.sh install`. `ExecStop` is `oai_gnb_env.sh uninstall`. Stopping the unit always runs uninstall.

`oai_gnb_env.sh uninstall` then:

- Unbinds only the BDF stored in `/var/tmp/oai-fhi72/vf_bdf` (the E810 VF). It does not unbind `8086:0d5c` or `8086:0d5d`.
- Writes `0` to `ice1`'s `sriov_numvfs`. It does not touch the ACC PF's `sriov_numvfs`.
- `umount /dev/hugepages`.
- Writes `0` to `nr_hugepages` for **every** NUMA node, for both 2 MB and 1 GB pools.
- `post_uninstall_check` treats **any** device still on `vfio-pci` as an error string. `err` only prints. It does not `exit`, so the ACC PF staying bound does not abort the script. The message is still wrong once ACC is in use: a clean ACC bind looks like a failed env uninstall.

`uninstall_target` calls `stop_stack` first, then `pkill -f` on `/etc/oai-gnb/conf/gnb.conf` (and the split conf paths), then `rm -rf` of `/opt/oai-gnb`, `/etc/oai-gnb`, and `/var/log/oai-gnb`.

`stop_stack` stops the same units, sleeps 1 second, `pkill -f` those conf paths, then `kill -9` any remaining `/opt/oai-gnb/bin/nr_softmodem`. `oai-du.service` itself has `TimeoutStopSec=10` and `Restart=no`, so a DU that does not exit is SIGKILLed at 10 seconds.

### Hang: hugepage shrink while the DU or a BBDEV test still holds pages

`echo 0 | tee .../nr_hugepages` does not fail when pages are busy. The kernel blocks the write until every page in that pool is free. The `tee` sits in uninterruptible sleep. `|| true` never runs. `TimeoutStopSec=60` on `oai-gnb-env` does not reap a process stuck in that sleep, so `deploy.sh install` and `deploy.sh uninstall` stay stuck on `systemctl stop` and the image is never copied.

That write runs on every node, including NUMA 0, which is where this DU allocates (`DPDK_NUMA_NODE=0`, 8192 × 2 MB). Two holders matter:

- `nr_softmodem`, if `oai-du` has not finished leaving DPDK. The combined `systemctl stop` relies on `After=`/`Requires=` to stop the DU before the env unit. `TimeoutStopSec=10` then SIGKILLs the DU. Hugepage teardown after SIGKILL is not instantaneous, and the env `ExecStop` starts as soon as systemd considers the DU stopped.
- `dpdk-test-bbdev`, if it is still running from G0. It is not in the gNB cgroup, so `systemctl stop` does not kill it, and the following hugepage write waits on it forever.

`hugepages()` on the next `oai_gnb_env.sh install` writes `8192` back to every node. That write blocks the same way if the shrink never finished. `TimeoutStartSec=120` then fails the env unit. The script has `set -Eeuo pipefail` and `trap cleanup_on_error ERR`, so a real failure calls `uninstall` again and issues another shrink. A blocked `tee` never reaches that trap.

### Die: DU killed on a live ACC queue, then the next init uses a wedged VF

`nrLDPC_coding_aal` holds the ACC VF open for the whole DU lifetime (`rte_bbdev_start`, one encode queue, one decode queue). `stop_stack` and the 10 second stop timeout do not FLR that VF and do not restart `pf_bb_config`.

Intel's own note on `pf_bb_config`: stop the DU first, and only then restart the daemon; a PF FLR requires a full reconfigure; a VF FLR flushes that VF's queues without reconfiguring the PF. This deploy path does none of those. It SIGKILLs the process that owns the queues.

The next `oai-du` start then either:

- `AssertFatal` in `nrLDPC_coding_init` (`no bbdev found`, queue configure failed, `rte_bbdev_start` failed). `Restart=no`, so the unit stays dead. This is the init **die**.
- or sits inside `rte_bbdev_setup_queues` / enqueue on a card that `pf_bb_config` has not reset. `TimeoutStartSec=120`, then systemd kills the DU. This is the init **hang**.

`pf_bb_config` itself is not stopped by `systemctl stop oai-du` or `oai-gnb-env`, which is what we want, but a daemon that already logged `Fatal error` is not a healthy daemon. The next DU must not be the thing that discovers that.

### Die: `pkill -f` and `rm -rf /etc/oai-gnb`

`pkill -f "/etc/oai-gnb/conf/gnb.conf"` matches any process whose command line contains that string. `nr_softmodem -O /etc/oai-gnb/conf/gnb.conf` is the intended match. A `pf_bb_config` line that also contains that path, or a shell that launched both, dies with the DU. The VF then rejects BBDEV until the daemon is started again, and the next DU hits the assert above.

`uninstall_target` deletes all of `/etc/oai-gnb`. A UUID or ACC cfg stored there is gone. `install_target` then `cp -a`s the image over `/etc/oai-gnb`. Extra files that are not in the image survive `cp -a`, but they do not survive the uninstall that often precedes a clean image. The packaged `gnb.conf` replaces the live one:

- Image conf has `_aal`, daemon or UUID missing → next `deploy.sh start` dies in `nrLDPC_coding_init`.
- Image conf has no `_aal` → next start is CPU LDPC, with no error. The upgrade looks fine and the offload is simply gone.

`install_target` also installs the image's `oai-du.service` over `/usr/lib/systemd/system/oai-du.service`. A hand-added `After=pf-bb-config.service` that is not in the image unit is removed at upgrade. The following start can launch the DU before the daemon. Same assert.

### `vfio-pci` parameters are not part of env install

`vf_bind` runs `modprobe vfio-pci` with no arguments. `modprobe` does not change parameters of a module that is already loaded, and `uninstall` never `rmmod`s it. So `enable_sriov=1 disable_idle_d3=1` survives an install/uninstall **only while the module stays loaded**.

`disable_idle_d3=1` is required for ACC100. A reboot, or any later cleanup that reloads `vfio-pci` without that parameter, lets the PF enter idle D3. The next `pf_bb_config` or `rte_dev_probe` then hangs the device. Env install will not repair it, because its `modprobe` is a no-op.

`post_uninstall_check` must not be "fixed" later by unbinding every `vfio-pci` device. That would drop the ACC PF on every gNB uninstall and force a full `pf_bb_config` from cold start before the DU can use `_aal`.

### Rules for a later image upgrade once ACC is in the conf

These are design rules. They are not implemented.

1. Stop `oai-du` and wait until `nr_softmodem` is gone and `HugePages_Free` equals `HugePages_Total` before anyone stops `oai-gnb-env`. If the DU is still alive at 8 seconds, do not let `TimeoutStopSec=10` SIGKILL it while `_aal` is set. Stop the DU, VF-FLR the ACC VF (not the PF), then start `pf_bb_config` again, then stop the env unit.
2. Kill `dpdk-test-bbdev` before any hugepage write. Confirm no process has `/dev/hugepages` mapped (`grep hugepages /proc/*/maps` is enough).
3. Do not `rmmod vfio-pci`. Do not unbind `0d5c` / `0d5d` from the env uninstall path.
4. Keep `/var/lib/oai-acc100/uuid` and the ACC cfg there. `deploy.sh uninstall` may delete `/etc/oai-gnb`. It must not delete `/var/lib/oai-acc100`.
5. The `pf_bb_config` command line must not contain `/etc/oai-gnb/conf/gnb.conf`.
6. Before `deploy.sh start`, if the **installed** `/etc/oai-gnb/conf/gnb.conf` contains `shlibversion = "_aal"`, require `pf_bb_config` alive and the VF on `vfio-pci`. If that check fails, refuse to start the DU. Do not let `AssertFatal` be the check.
7. An image build used while ACC is still on trial must ship the two profiles **without** `_aal`, and the live `/etc/oai-gnb/conf/gnb.conf` is patched only in the maintenance window of section 6.5. Shipping `_aal` inside the image before G4 has passed means every `deploy.sh install` turns a conf rollback into a DU that cannot boot.

---

## 6. Procedures

### 6.1 Preflight (cell stays up)

```bash
lspci -d 8086:0d5c          # ACC100 PF. Record BDF. Must not be 0000:11:09.0
lspci -d 8086:0d5d          # empty until the VF is created
lspci -d 8086:1592 || true  # E810, just to confirm it is a different device
systemctl is-active oai-gnb-env oai-du
grep -E 'Hugepagesize|^HugePages_Total|^HugePages_Free' /proc/meminfo
test -d /opt/dpdk-22.11.11/lib/x86_64-linux-gnu
```

Stop here if `oai-gnb-env` is not active, if the ACC PF is missing, or if the only baseband device you see is the E810 VF.

Confirm IOMMU is already on (`intel_iommu=on iommu=pt` in the kernel cmdline). Do not edit grub in this upgrade.

### 6.2 Build (cell stays up)

In `scripts/gnb/gnb_manager.sh`, on the v26.w14 `build_oai` line only, add `--build-lib ldpc_aal` and stamp `LATUAN_ACC100_LDPC`. That is the only script change. It sets `ENABLE_LDPC_AAL=ON`.

```bash
./scripts/gnb/gnb_manager.sh build-gnb
ls sources/openairinterface5g-v26.w14/cmake_targets/oran_fhi72_gnb_build/build/libldpc_aal.so
ldd sources/openairinterface5g-v26.w14/cmake_targets/oran_fhi72_gnb_build/build/libldpc_aal.so | grep dpdk
```

`ldd` must show `/opt/dpdk-22.11.11`. A hit under `/usr/local` is a failed build. Do not package it.

Do not pass `--build-lib ldpc_aal` on `ran_sim_build`. Do not clean DPDK or xRAN for this step. An OAI rebuild is enough.

The image step already copies every `*.so` from the build directory into `/opt/oai-gnb/lib`. A full image install is optional. The fast install in section 6.5 copies two files.

### 6.3 ACC VF (cell stays up)

`disable_idle_d3=1` is required for ACC100. This `modprobe` does not rebind `ice1`.

```bash
sudo modprobe vfio-pci enable_sriov=1 disable_idle_d3=1
sudo /opt/dpdk-22.11.11/bin/dpdk-devbind.py --bind=vfio-pci <PF>
```

Build once:

```bash
cd sources/pf-bb-config && ./build.sh
sudo mkdir -p /var/lib/oai-acc100
uuidgen | sudo tee /var/lib/oai-acc100/uuid
```

Keep that file. The conf and the daemon must use the same string. Do not use the Intel example UUID `00112233-4455-6677-8899-aabbccddeeff` on this host.

```bash
sudo ./pf_bb_config ACC100 \
  -v "$(cat /var/lib/oai-acc100/uuid)" \
  -c acc100/acc100_config_1vf_5g.cfg
echo 1 | sudo tee /sys/bus/pci/devices/<PF>/sriov_numvfs
/opt/dpdk-22.11.11/bin/dpdk-devbind.py -s | grep -A2 -i baseband
```

Pass: the log contains `ACC100 PF [<PF>] configuration complete!`, and `<PF>` with function `.1` shows `drv=vfio-pci`. Leave the process running. Log file is `/var/log/pf_bb_cfg_<PF>.log`.

If `sriov_numvfs` already has a value, write `0` first, then `1`. Do not write `1` on top of an existing VF.

Engineering-sample warning in that log (`Not on DDR PRQ version`) means the card is pre-PRQ. Record it. Do not continue to G4 on that card without noting it; Intel’s own note is to use the PRQ part. G0 can still be run.

### 6.4 Make the daemon survive reboot (design of the unit)

A shell `pf_bb_config` dies with the session and after reboot, and the next DU start then asserts in `nrLDPC_coding_init`. The unit to add, when implementation is requested:

| Field | Value |
|---|---|
| Unit name | `pf-bb-config.service` |
| `After` / `Before` | After `systemd-modules-load.service`. Before `oai-du.service`. |
| Relationship to `oai-gnb-env` | None. No `Requires`, no `Wants`, no `PartOf`. |
| `Type` | `simple` (the process stays in the foreground in VFIO mode) |
| `Restart` | `on-failure` |
| `ExecStart` | `/usr/local/bin/pf_bb_config ACC100 -v <UUID> -c /var/lib/oai-acc100/acc100_config_1vf_5g.cfg` |
| ExecStartPre | `modprobe vfio-pci enable_sriov=1 disable_idle_d3=1`, bind the PF if it is not already on `vfio-pci`, then `echo 1 > .../sriov_numvfs` only when the current value is 0 |

Copy `pf_bb_config` to `/usr/local/bin` and `acc100_config_1vf_5g.cfg` to `/var/lib/oai-acc100/`. Do not put either under `/etc/oai-gnb` or `/opt/oai-gnb`: `deploy.sh uninstall` deletes both trees, and `install` overwrites them from the image (section 5A). The unit command line must not contain `/etc/oai-gnb/conf/gnb.conf`. Enable the unit only after G0 has passed once from the shell.

`oai-du.service` should gain `After=pf-bb-config.service` and `Wants=pf-bb-config.service`, not `Requires=`. If the ACC unit is down, a later CPU-LDPC conf must still be allowed to start. The assert only happens when the conf asks for `_aal` and the VF is dead.

### 6.5 Maintenance window

```bash
systemctl stop oai-du
# do not stop oai-gnb-env
test "$(systemctl is-active oai-gnb-env)" = active

STAMP=$(date +%Y%m%d-%H%M%S)
sudo mkdir -p /var/backups/oai-acc100-$STAMP
sudo cp -a /opt/oai-gnb/bin/nr_softmodem /var/backups/oai-acc100-$STAMP/
sudo cp -a /etc/oai-gnb/conf/gnb.conf /var/backups/oai-acc100-$STAMP/gnb.conf
```

G0, still inside the window, DU stopped, `pf_bb_config` still running:

```bash
sudo /opt/dpdk-22.11.11/bin/dpdk-test-bbdev \
  -c F0 -a <VF> --vfio-vf-token="$(cat /var/lib/oai-acc100/uuid)" -- \
  -c validation -v ./ldpc_dec_default.data
```

`-c F0` uses cores 4–7, which are free only because `oai-du` is stopped. Do not pick cores 0–1 or 16–31.

On G0 failure: do not copy the new binary. `systemctl start oai-du` with the backup still in place (nothing was overwritten yet). End the window.

On G0 success, fast install from the build directory `BUILD=sources/openairinterface5g-v26.w14/cmake_targets/oran_fhi72_gnb_build/build`:

```bash
sudo install -m 755 "$BUILD/nr-softmodem" /opt/oai-gnb/bin/nr_softmodem
sudo install -m 644 "$BUILD/libldpc_aal.so" /opt/oai-gnb/lib/libldpc_aal.so
sudo ldconfig
```

`LD_LIBRARY_PATH` of `oai-du.service` is already `/opt/oai-gnb/lib:/opt/dpdk-22.11.11/lib/x86_64-linux-gnu`. No unit edit is required for the library to be found.

Then patch **the running file** `/etc/oai-gnb/conf/gnb.conf`, and the same block in the two source profiles so the next `deploy.sh` staging does not drop it. Source profiles:

- `configs/gnb/002.gnb.sa.e2e.band79.100mhz.273.fhi72.4x4.conf`
- `configs/gnb/002.gnb.sa.tm.band79.100mhz.273.fhi72.4x4.dl.256qam.conf`

If the window is an E2E test (`MODE_IDX=3`), the live `gnb.conf` must be the E2E profile plus the block. If the window is TM DL (`MODE_IDX=2`), stage the TM DL profile first, then the block. Do not leave an E2E conf in place while `MODE_IDX=2`, or the reverse. Switching `MODE_IDX` is an edit of the env file and a DU restart. It does not require an `oai-gnb-env` restart.

```text
loader = {
  ldpc = {
    shlibversion = "_aal";
  };
};

nrLDPC_coding_aal = {
  dpdk_dev = "<VF>";
  vfio_vf_token = "<contents of /var/lib/oai-acc100/uuid>";
  is_t2 = 0;
};
```

`<VF>` is the full BDF `0000:XX:YY.Z`. The short form `XX:YY.Z` is also accepted; `normalize_dpdk_dev()` expands it.

Leave unset: `dpdk_core_list`, `dpdk_file_prefix`, `num_harq_codeblock`. Defaults are “no second EAL”, prefix `b6` (unused when EAL is already up), and 512 HARQ blocks of 32 kB. ACC100 HARQ is on-card. Do not raise 512 on the first run.

```bash
systemctl start oai-du
```

### 6.6 First minute

```bash
journalctl -u oai-du -n 200 --no-pager
grep -E 'ldpc_aal|bbdev|EAL initialization|skipping EAL' /var/log/oai-gnb/du.log
```

Pass (G1), all four:

- the process maps `libldpc_aal.so` (`grep ldpc_aal /proc/$(pidof nr_softmodem)/maps`)
- `Probing DPDK device <VF> ... succeeded, skipping EAL initialization`
- `bbdev <VF> found` and `using bbdev`
- `Found LDPC encoding queue` and `Found LDPC decoding queue`

Fail, any one of these, and go to section 9 immediately:

- `EAL initialization failed` or a second `rte_eal_init`
- `no bbdev found` / `bbdev <VF> not found`
- `nrLDPC_coding_aal.dpdk_dev was not provided`
- `Assertion` in `add_dev` or `rte_bbdev_start`
- `oai-du` exits before 60 s (`Restart=no`, so it stays down)

`initializing EAL before continuing` means xRAN never received the VF. The conf key is wrong or `pf_bb_config` is dead. Do not add `dpdk_core_list`.

---

## 7. Test windows after G1

One mode per window. Between them, stop only `oai-du`, swap `/etc/oai-gnb/conf/gnb.conf` and `MODE_IDX`, start `oai-du`.

**TM DL.** `MODE_IDX=2`. Source `002.gnb.sa.tm.band79.100mhz.273.fhi72.4x4.dl.256qam.conf` plus the section 6.5 block. Run 10 minutes. This mode encodes only (`ulsch_slot_bitmap == 0`); it does not prove decode. Record MAC TX and whether the slot clock jumped.

**E2E.** `MODE_IDX=3`. Source `002.gnb.sa.e2e.band79.100mhz.273.fhi72.4x4.conf` plus the same block. Attach, then iperf DL at MCS 26 for at least 60 s. Record MAC, iperf, BLER, and how often `skip_rx` fires compared with the CPU-LDPC run.

UL TM confs stay without the block. A UL phy-test of ACC decode is a later window and needs its own conf edit, which this design does not include.

---

## 8. If G0 fails on the DPDK 22.11 ACC100 driver

OAI documents [DPDK commit fdde63a1](https://github.com/DPDK/dpdk/commit/fdde63a1dfc129d0a510a831aa98253b36a2a1cd) for ACC100 on DPDK before 24.11. Apply it only when `dpdk-test-bbdev` fails with an ACC100 queue or interrupt error, not for a bind or UUID mistake.

Rebuild this tree’s DPDK in place (`./scripts/gnb/dpdk_manager.sh`), reinstall to `/opt/dpdk-22.11.11`, then rerun G0. Do not point OAI at another prefix. After a DPDK rebuild, the next `build-gnb` must be a clean OAI link so `liboran_fhlib_5g.so` and `libldpc_aal.so` both resolve the same DPDK. That is a wider window: take the backup in section 6.5 first, and be ready to restore `/opt/dpdk-22.11.11` as well.

---

## 9. Rollback (one DU restart)

```bash
systemctl stop oai-du
sudo cp -a /var/backups/oai-acc100-$STAMP/nr_softmodem /opt/oai-gnb/bin/nr_softmodem
sudo cp -a /var/backups/oai-acc100-$STAMP/gnb.conf /etc/oai-gnb/conf/gnb.conf
sudo rm -f /opt/oai-gnb/lib/libldpc_aal.so
systemctl start oai-du
```

The backup conf has no `_aal` key, so the old binary uses CPU LDPC even if the `.so` is left behind. Removing the `.so` makes a stale conf fail at load instead of half-offloading.

Leave `pf_bb_config` running. It does not affect the CPU path. Do not FLR the ACC PF (`echo 1 > .../reset`) while the DU is up. A PF FLR needs `pf_bb_config` again from a cold start. A VF FLR does not.

Confirm rollback: `du.log` has no `libldpc_aal`, and `oai-gnb-env` never left `active`.

---

## 10. Failure playbook

| Symptom | Cause | Next action |
|---|---|---|
| `sriov_numvfs: No such file` | `vfio-pci` loaded without `enable_sriov=1` | `echo 1 > /sys/module/vfio_pci/parameters/enable_sriov`, rebind the PF, retry section 6.3 |
| VF exists but `unused=vfio-pci` | VF not bound | `dpdk-devbind.py --bind=vfio-pci <VF>` |
| bbdev test: `VFIO_DEVICE_FEATURE_PCI_VF_TOKEN` | UUID mismatch, or `pf_bb_config` died | Restart the daemon with the UUID file, then the test. Do not generate a second UUID. |
| DU assert `no bbdev found` | Daemon died, or VF not in the xRAN allow-list | Section 9 if the cell must come back. Otherwise check `ps` for `pf_bb_config` and the conf BDF. |
| Log says `initializing EAL` | `shlibversion` is not exactly `_aal`, or `is_t2` is 1, so xRAN set `XRAN_BBDEV_NOT_USED` | Fix the two conf keys. Restart only `oai-du`. |
| `Cannot get hugepage information` | Someone ran a hugepage reset, or the test binary ran as non-root | Do not reallocate. Start the old DU. Check `HugePages_Free` first. |
| E810 VF missing after the window | `oai-gnb-env` was restarted or `deploy.sh stop` was used | Out of this design. Bring the env unit back with the existing SR-IOV procedure, then start the old DU. |
| TM DL rate drops > 5% | Single encode queue plus `encode_mutex` is slower than AVX-512 CPU LDPC | Rollback. Do not add queues in the same window. |
| E2E BLER up, BBDEV start was clean | Decoder iteration budget | Next window only: raise `max_ldpc_iterations`, one step, same conf otherwise. If it does not recover MCS 26, rollback. |
| `pf_bb_config` log `Fatal error` then `Cluster reset` | Card recovered itself, usually after `stop_stack` SIGKILL | Do not start the DU on that daemon. VF-FLR the ACC VF, restart `pf_bb_config`, then start the DU. |
| `deploy.sh install` stuck on `systemctl stop` | `oai_gnb_env.sh uninstall` blocked in `echo 0 > nr_hugepages` | Section 5A. Kill `dpdk-test-bbdev` if it is running. Do not stop `oai-gnb-env` until `HugePages_Free == HugePages_Total`. Do not `kill -9` the `tee`; it is in D state until the pages are free. |
| Next DU dies in `nrLDPC_coding_init` right after an image install | Packaged `gnb.conf` has `_aal`, and the daemon, UUID, or VF did not survive `uninstall` / SIGKILL | Section 5A rules 4–7. Start CPU LDPC (restore the backup conf) if the cell must come back. |

---

## 11. Files to touch when implementation is requested

| File | Change |
|---|---|
| `scripts/gnb/gnb_manager.sh` | `--build-lib ldpc_aal` on the v26.w14 FHI `build_oai` line. Stamp `LATUAN_ACC100_LDPC`. |
| `configs/systemd/pf-bb-config.service` | New unit, section 6.4. |
| `configs/systemd/oai-du.service` | `After=` and `Wants=` the new unit. Not `Requires=`. |
| `configs/gnb/002.gnb.sa.e2e.band79.100mhz.273.fhi72.4x4.conf` | Section 6.5 block. |
| `configs/gnb/002.gnb.sa.tm.band79.100mhz.273.fhi72.4x4.dl.256qam.conf` | Section 6.5 block. |

No edit to `nrLDPC_coding_aal.c`, `oran-config.c`, xRAN, BLER targets, `max_ldpc_iterations`, `skip_rx_if_busy`, or the UL TM confs, unless a gate in section 4 fails and a follow-up design says so.

No edit yet to `scripts/gnb/deploy.sh` or `scripts/gnb/env/oai_gnb_env.sh`. Section 5A is the spec for that later change. Until those scripts follow D13–D16, an ACC conf is installed by the section 6.5 file copy, not by `deploy.sh install`.

DPDK source changes only under section 8.

---

## 12. Out of scope

- 1024QAM.
- UL phy-test on ACC100.
- More than one VF, 4G queues, or raising `nb_queues` above the stock 1 encode + 1 decode.
- Replacing `/opt/dpdk-22.11.11` for any reason other than section 8.
- Restarting `oai-gnb-env`, rebinding `ice1`, or editing hugepages.
- Changing `deploy.sh` or `oai_gnb_env.sh` in this design pass. The install/uninstall hazards are recorded in section 5A and are not patched here.
- Copying the OAI sample BLER targets (0.15 / 0.35) onto this cell.
