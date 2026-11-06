# Guide: gNB install / uninstall with ACC100

**Author:** LATUAN · **2026.10.28**  
**Tag:** `LATUAN_ACC100_LDPC`  
**Status:** operations guide. Does not change `deploy.sh` or `oai_gnb_env.sh`.  
**Related:** `docs/gNB_256_acc100_design.md` §5A (why the scripts break), `docs/LATUAN_ACC100_package_design.md` (host `.deb`), `docs/design/LATUAN_DPDK_ACC100_debug_cli.md` (GET checks).

Use this file when an image install, uninstall, or `deploy.sh stop` leaves the cell down, hugepages stuck, or the next DU dying in `nrLDPC_coding_init`.

---

## 1. Two products, two lifetimes

| Product | What it owns | How you install | How you remove | Survives `deploy.sh uninstall`? |
|---|---|---|---|---|
| **ACC100 host env** | `pf_bb_config`, `acc100_config_vf_5g.cfg`, `pf-bb-config.service` + `@`, VFIO token, `vfio-pci` options | Once: `sudo ./scripts/gnb/acc100_manager.sh install` then `systemctl start pf-bb-config` | `sudo ./scripts/gnb/acc100_manager.sh uninstall` only while `oai-du` is **stopped** | **Yes** — files live under `/usr/local/bin`, `/var/lib/oai-acc100`, `/usr/lib/systemd/system/pf-bb-config*` |
| **gNB image** | `nr_softmodem`, `libldpc*.so`, `/etc/oai-gnb`, `oai-du` / `oai-gnb-env` | `sudo ./deploy.sh install` | `sudo ./deploy.sh uninstall` | No — deletes `/opt/oai-gnb` and `/etc/oai-gnb` |

ICE and DPDK are a third lifetime (`/opt/dpdk-22.11.11`, `ice1`). Do not uninstall them with the gNB.

`_aal` in `gnb.conf` is a **gNB image** setting. It is not created by the ACC `.deb`. The `.deb` does not write `libldpc_aal.so`.

```text
ice-dkms  →  DPDK /opt  →  acc100-pf-bb-config (once)  →  deploy.sh install (many)
```

Never reverse that with `deploy.sh uninstall` expecting the card to go away. The card and the daemon must stay.

---

## 2. What `deploy.sh` does today (the bugs)

`deploy.sh` was written for the E810 VF only. It does **not** know ACC100.

| Command | What it actually does | ACC damage |
|---|---|---|
| `install` / `install-only` | `systemctl stop` `oai-du` **and** `oai-gnb-env`, then `cp -a` `/opt/oai-gnb` and `/etc/oai-gnb`, replace `oai-*.service` | Stops env → hugepage shrink can **hang**. Replaces live `gnb.conf` (may add or drop `_aal`). Overwrites a hand `After=pf-bb-config` on `oai-du.service`. Does **not** start ACC. |
| `uninstall` | `stop_stack`, `pkill -f /etc/oai-gnb/conf/gnb.conf`, `rm -rf` `/opt/oai-gnb` `/etc/oai-gnb` `/var/log/oai-gnb` | Same hang. If daemon argv contained that conf path, `pkill` **kills `pf_bb_config`**. Token in `/etc/oai-gnb` would be gone (use `/var/lib/oai-acc100` instead). |
| `stop` / `restart` | Same unit stop as install | Tears down E810 VF (`sriov_numvfs=0` on `ice1`) and hugepages. Leaves ACC queues dirty if the DU was SIGKILL’d (`TimeoutStopSec=10`). |

`oai-gnb-env` `ExecStop` = `oai_gnb_env.sh uninstall`:

1. Unbind E810 VF only (`/var/tmp/oai-fhi72/vf_bdf`). Does not unbind `0d5c` / `0d5d`.
2. Write `0` to `ice1` `sriov_numvfs`. Does not touch ACC `sriov_numvfs`.
3. `echo 0 > nr_hugepages` on **every** NUMA node. If any process still maps hugepages, this `tee` goes **D-state** and `deploy.sh` never returns.
4. `post_uninstall_check` prints an error for **any** leftover `vfio-pci` device. A healthy ACC PF looks like a failed env uninstall. Ignore that line. Do not “fix” it by unbinding every `vfio-pci` device.

---

## 3. Do not / do

| Do not | Do |
|---|---|
| `deploy.sh install` / `uninstall` / `stop` to turn ACC on or off | `systemctl start\|stop pf-bb-config` (or the live `acc100-*` units). DU stays up only if you are not touching hugepages. |
| `systemctl restart oai-gnb-env` while `nr_softmodem` or `dpdk-test-bbdev` holds pages | `systemctl stop oai-du` first. Wait until `HugePages_Free == HugePages_Total` (or only the leftover you expect). Then, if you must, stop env. |
| `deploy.sh install` to swap `_aal` onto a live cell | Fast path: stop **only** `oai-du`, copy `nr_softmodem` + `libldpc_aal.so`, patch the **running** `/etc/oai-gnb/conf/gnb.conf`, start `oai-du`. |
| Put UUID / ACC cfg under `/etc/oai-gnb` | `/var/lib/oai-acc100/uuid` and `acc100_config_vf_5g.cfg` |
| Put `gnb.conf` in the `pf_bb_config` argv | `-p <PF> -v <token> -c /var/lib/oai-acc100/acc100_config_vf_5g.cfg` |
| `rmmod vfio-pci` on uninstall | Leave the module loaded with `enable_sriov=1 disable_idle_d3=1` |
| `echo 0 > …/0000:23:00.0/sriov_numvfs` | Leave ACC VFs. Recreate only when the count is already 0 and DDR has trained. |
| Bind or unbind `0000:11:09.0` from an ACC script | That BDF is the E810 VF |
| Two `pf_bb_config` on the same `-p` | One daemon per PF. Extra DUs = `vf-count`, not a second process |
| `dpkg -i` ACC while the hand daemon is up, then `systemctl start` | Enable the unit, **stop the hand daemon**, then start the unit |
| `dpkg -P acc100-pf-bb-config` if the gNB token must stay | `dpkg -r` keeps `/var/lib/oai-acc100/uuid`. Purge deletes it and the next install `uuidgen`s a **new** token |
| `kill -9` the stuck `tee` on `nr_hugepages` | It is D-state. Free the holders (`nr_softmodem`, `dpdk-test-bbdev`). The write then finishes. |

---

## 4. Safe sequences

### 4.1 Install gNB image while ACC must stay up (CPU LDPC image, or `_aal` already proven)

```text
1. Confirm no dpdk-test-bbdev
2. systemctl stop oai-du
3. Wait: pgrep nr_softmodem is empty
         grep -E '^HugePages_' /proc/meminfo
         Free == Total  (or only maps you accept)
4. ONLY THEN: sudo ./deploy.sh install     # this still stops oai-gnb-env
5. Check: pf_bb_config still running
          lspci -D -d 8086:0d5d still present
          /var/lib/oai-acc100/uuid unchanged
          grep shlibversion /etc/oai-gnb/conf/gnb.conf
6. If conf has _aal: require daemon + ACC VF vfio-pci before start
   If conf has no _aal: CPU path — ACC may stay running
7. systemctl start oai-gnb-env     # if install left it stopped
   systemctl start oai-du
```

If you can avoid step 4, do: copy binaries by hand and **do not** stop `oai-gnb-env`. That is the fast path in `gNB_256_acc100_design.md` §5 / §6.5.

### 4.2 Uninstall gNB image, keep ACC

```text
1. systemctl stop oai-du
2. Wait hugepages free (same as 4.1)
3. sudo ./deploy.sh uninstall
4. Confirm still present:
     ps -fp "$(pgrep -x pf_bb_config || echo)"
     ls /var/lib/oai-acc100/uuid
     lspci -D -d 8086:0d5c
5. Do NOT: acc100_manager.sh uninstall
           dpkg -r acc100-pf-bb-config
           rm -rf /opt/pf-bb-config          # live hand tree, if any
           rmmod vfio-pci
```

### 4.3 Uninstall ACC (rare; card / package upgrade)

```text
1. If gnb.conf has _aal: stop oai-du, remove _aal (or restore CPU conf), start oai-du
   OR leave DU stopped for the whole window
2. acc100_manager.sh uninstall refuses while oai-du is active — that is correct
3. sudo ./scripts/gnb/acc100_manager.sh uninstall     # dpkg -r, keeps uuid
   sudo dpkg -P acc100-pf-bb-config                   # only if you accept a new token
4. Do not uninstall DPDK or ICE here
```

On this chassis, if the **NGUYEN** `acc100-*` units are the live ones, use `scripts/gnb/acc100_latuan_wipe.sh` then `acc100_nguyen_hold.sh restore`. Do not `rm -rf /opt/pf-bb-config` (that tree belongs to those units).

### 4.4 First ACC `.deb` on a host that already has a hand daemon

```text
1. Write the live token BEFORE dpkg -i, or postinst uuidgen will invent a new one:
     sudo mkdir -p /var/lib/oai-acc100
     echo -n '<live-uuid>' | sudo tee /var/lib/oai-acc100/uuid
2. sudo ./scripts/gnb/acc100_manager.sh install
   # postinst enables the unit and must NOT start if pf_bb_config is already running
3. systemctl stop oai-du
4. Stop the hand daemon (or acc100_nguyen_hold.sh detach)
5. systemctl start pf-bb-config
6. Wait log: configuration complete  AND  DDR Training completed
7. Confirm virtfn0 / 0d5d, then start oai-du
```

Two daemons on one PF = exclusive VFIO fail or a silent reconfigure. Never skip step 4.

---

## 5. Symptom → fix

### A. `deploy.sh install` or `uninstall` hung on `systemctl stop`

**Cause:** `oai_gnb_env.sh uninstall` is blocked in `echo 0 > nr_hugepages`. A holder still has `/dev/hugepages` mapped.

**Fix (order):**

```bash
pgrep -a nr_softmodem
pgrep -a dpdk-test-bbdev
pgrep -a pf_bb_config          # must stay; it does not use this pool
grep -E '^HugePages_' /proc/meminfo
# if test-bbdev:
sudo kill "$(pgrep -x dpdk-test-bbdev)"     # TERM, then wait
# if nr_softmodem still there after oai-du failed:
sudo systemctl stop oai-du
# do NOT kill -9 the tee writing nr_hugepages
# when Free == Total, the hung systemctl stop returns; rerun install/uninstall only if still needed
```

Do not `systemctl restart oai-gnb-env` to “unstick” it. That queues another shrink.

### B. Next DU dies: `no bbdev found` / `nrLDPC_coding_init`

**Cause:** `_aal` is on, but no ACC VF, no daemon, token mismatch, or queues left dirty after SIGKILL.

**Fix — cell first (CPU LDPC):**

```bash
systemctl stop oai-du
# restore backup conf without _aal, or comment shlibversion / dpdk_dev / vfio_vf_token
sudo cp -a /var/backups/oai-acc100-<stamp>/gnb.conf /etc/oai-gnb/conf/gnb.conf
# optional: sudo rm -f /opt/oai-gnb/lib/libldpc_aal.so
systemctl start oai-du
# leave pf_bb_config running
```

**Fix — keep `_aal`:**

```bash
systemctl stop oai-du
# VF-FLR the ACC VF only (not 0000:23:00.0, not 0000:11:09.0)
echo 1 | sudo tee /sys/bus/pci/devices/0000:24:00.0/reset
# restart daemon (one of):
sudo systemctl restart pf-bb-config          # package unit
# or the live three-step acc100-bind-pf / acc100-pf-bb / acc100-bind-vf
# wait: configuration complete + DDR Training completed
TOKEN=$(cat /var/lib/oai-acc100/uuid)        # or /etc/oai-gnb/conf/acc100.env
grep vfio_vf_token /etc/oai-gnb/conf/gnb.conf   # must match TOKEN
lspci -D -d 8086:0d5d
python3 /opt/dpdk-22.11.11/bin/dpdk-devbind.py -s | grep -E '0d5c|0d5d|11:09.0'
systemctl start oai-du
# 60 s: libldpc_aal.so, skipping EAL, bbdev 0000:24:00.0 found
```

If `pf_bb_config` log shows `Fatal error` / `Cluster reset` after the old SIGKILL, do not start the DU on that process. VF-FLR + daemon restart first.

### C. Log `initializing EAL` then fail

**Cause:** xRAN did not publish the ACC VF (`shlibversion` not exactly `_aal`, or `is_t2 = 1`).

**Fix:** edit the **running** `gnb.conf` only. Restart `oai-du` only. Do not add `dpdk_core_list`. Do not put `0000:24:00.0` in `fhi_72.dpdk_devices`.

### D. Token / UUID mismatch after install or purge

**Cause:** `postinst` `uuidgen` because `/var/lib/oai-acc100/uuid` was missing; or `dpkg -P` deleted it; or image `gnb.conf` has the old string.

**Fix:** one UUID everywhere. Do not invent a second one.

```bash
# pick the daemon's -v (ps) as source of truth
sudo tee /var/lib/oai-acc100/uuid <<<'<that-uuid>'
# set vfio_vf_token in /etc/oai-gnb/conf/gnb.conf to the same string
systemctl stop oai-du
systemctl restart pf-bb-config    # or live acc100-pf-bb
systemctl start oai-du
```

### E. E810 VF gone after `deploy.sh stop` / env restart

**Cause:** env uninstall wrote `sriov_numvfs=0` on `ice1`. Not an ACC bug.

**Fix:** start `oai-gnb-env` again (existing SR-IOV path). Confirm `0000:11:09.0` `vfio-pci`, VF MAC / VLAN 1101. Then start `oai-du`. Do not recreate ACC VFs as part of this.

### F. `sriov_numvfs: No such file` on the ACC PF

**Cause:** `vfio-pci` loaded without `enable_sriov=1`.

**Fix:**

```bash
echo 1 | sudo tee /sys/module/vfio_pci/parameters/enable_sriov
echo 1 | sudo tee /sys/module/vfio_pci/parameters/disable_idle_d3
# persist: /etc/modprobe.d/vfio-acc100.conf
# options vfio-pci enable_sriov=1 disable_idle_d3=1
```

Do not `rmmod vfio-pci` while the E810 VF is live.

### G. Image install silently dropped offload

**Cause:** packaged `gnb.conf` has no `_aal`. CPU LDPC, no error.

**Fix:** not a crash. Either patch the running conf (fast path) or rebuild the image with the two 100 MHz 4×4 blocks after G0–G4. Do not “fix” by `deploy.sh install` of an `_aal` image until the daemon and VF are up.

### H. Image install then DU cannot boot (`_aal` in image, ACC down)

**Cause:** D16. Image shipped `_aal` before the host package / daemon was ready.

**Fix:** restore CPU `gnb.conf` (section B). Bring ACC with §4.4. Only then put `_aal` back.

### I. `post_uninstall_check` says leftover `vfio-pci`

**Cause:** ACC PF/VF still bound. Expected.

**Fix:** none. Confirm the leftover BDF is `0000:23:00.0` or `0000:24:00.0`, not a stray E810.

### J. Hugepage write hangs again on the next `oai-gnb-env` start

**Cause:** the previous shrink never finished; `hugepages()` writes `8192` and blocks the same way. `TimeoutStartSec=120` fails; the env script may `uninstall` again.

**Fix:** same as A. Get Free == Total first. Then `systemctl start oai-gnb-env`.

---

## 6. GET checks after any install/uninstall

Do not use SET commands here. Full cookbook: `docs/design/LATUAN_DPDK_ACC100_debug_cli.md`.

```bash
systemctl is-active oai-du oai-gnb-env pf-bb-config acc100-pf-bb
pgrep -a nr_softmodem
pgrep -a pf_bb_config
pgrep -a dpdk-test-bbdev || echo none
grep -E '^HugePages_' /proc/meminfo
python3 /opt/dpdk-22.11.11/bin/dpdk-devbind.py -s | grep -E '11:09.0|0d5c|0d5d'
cat /sys/bus/pci/devices/0000:23:00.0/sriov_numvfs
cat /sys/module/vfio_pci/parameters/enable_sriov
cat /sys/module/vfio_pci/parameters/disable_idle_d3
ls /var/lib/oai-acc100/uuid /etc/oai-gnb/conf/acc100.env 2>&1
grep -E 'shlibversion|dpdk_dev|vfio_vf_token|is_t2|dpdk_devices' /etc/oai-gnb/conf/gnb.conf
ls /opt/oai-gnb/lib/libldpc*
grep -E 'skipping EAL|libldpc_aal|bbdev|no bbdev' /var/log/oai-gnb/du.log | tail
```

Healthy after a **gNB-only** reinstall with `_aal` intended:

- `oai-du` active, `oai-gnb-env` active
- one `pf_bb_config`, ACC VF `0d5d` `vfio-pci`, E810 `11:09.0` `vfio-pci`
- `gnb.conf` token = uuid file
- `libldpc_aal.so` present, log `skipping EAL` + `bbdev 0000:24:00.0 found`

Healthy after a **gNB uninstall** (ACC kept):

- no `nr_softmodem`
- daemon still running, uuid file still there, `0d5c` still present
- `/opt/oai-gnb` gone is OK

---

## 7. Decision: which command am I allowed to run?

```text
Need to swap gNB binary / image
        │
        ├─ ACC not in conf (_aal absent) ── deploy.sh install is the old path
        │                                    still stop oai-du first; watch hugepages
        │
        └─ ACC in conf or on trial ── stop oai-du only
                                      hand-copy binary + .so + patch conf
                                      do not deploy.sh install/stop

Need to remove gNB from disk
        └─ deploy.sh uninstall after oai-du stopped and hugepages free
           never acc100_manager.sh uninstall in the same step

Need to remove / upgrade ACC tools
        └─ DU on CPU LDPC or DU stopped
           acc100_manager.sh uninstall
           never deploy.sh uninstall for this
```

---

## 8. Files that must not share a path

| Keep out of `/opt/oai-gnb` and `/etc/oai-gnb` | Why |
|---|---|
| `pf_bb_config` binary | `uninstall` deletes `/opt/oai-gnb` |
| `acc100_config_vf_5g.cfg` | same |
| VFIO UUID | `uninstall` deletes `/etc/oai-gnb` |
| `pf-bb-config*.service` | `install` only ships `oai-*` units; do not copy ACC units into the gNB image |

`oai-du.service` may `After=` / `Wants=` `pf-bb-config.service`. That line lives in the **gNB** unit. A new image without it will start the DU before the daemon — check after every `deploy.sh install`.

---

## 9. This host (read before you type)

Snapshot changes. Re-run the GET list in §6.

As of 2026-10-25: E810 cell live, ACC path **off** (no `0d5d`, no `pf_bb_config`, no `_aal` in live `gnb.conf`). `deploy.sh uninstall` would still hang if hugepages are held. It would **not** remove a package that is not installed. Hand `/opt/pf-bb-config` and live `acc100-*.service` (if present again) are not the LATUAN deb — do not wipe them with `acc100_manager.sh uninstall` unless you intend to replace that stack.
