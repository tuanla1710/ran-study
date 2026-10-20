# O-RAN eCPRI at the DU

**Author:** LATUAN · **2026.10.20**

The DU in this tree speaks **O-RAN WG4 CUS over eCPRI**, split **8.2x**: frequency-domain IQ. Intel xRAN (`sources/o-du-phy-oran_f_release_v1.9`, libxran) owns the packets. OAI only drives it from `radio/fhi_72/` (`oai_oran_initialize` → `xran_open`).

The older OAI path `udp_ecpri_if5` (`radio/ETHERNET/`, described in `docs/analysis/Guide_to_Data_Processes_Related_to_eCPRI.md`) is a different interface: split 8, time-domain IQ, 256 samples per UDP packet, message type 64, no C-plane. The DU that faces an O-RU is the FHI 7.2 stack below.

Longer C-plane and U-plane call traces are in `docs/oran_fronthaul_data_path_analysis.md`.

## What the DU puts on the wire

Ethernet, ethertype **0xAEFE** (eCPRI), optional VLAN PCP 7, then the eCPRI header and the O-RAN application header. Transport is **DPDK** on a vfio-pci VF (jumbo MTU; lab config `mtu = 9000`). It is not UDP. The peer is the O-RU MAC in `fhi_72.ru_addr`. The NIC is `fhi_72.dpdk_devices`.

Common eCPRI header (`xran_pkt.h`): version, concatenation bit, message type, payload size, then **eAxC id** (`ecpri_xtc_id`) and sequence id (`seq_id`, `sub_seq_id`, `e_bit`).

| Message type | Value | DU role |
|---|---|---|
| IQ data (U-plane) | `0x00` | DU sends DL IQ, receives UL IQ |
| Real-time control (C-plane) | `0x02` | DU **sends** only. An O-DU that receives C-plane logs an error and drops it |
| One-way delay | `0x05` | Present in the library; not processed once xRAN is `XRAN_RUNNING` |
| Bit sequence, generic data, remote memory, reset, event | `0x01`, `0x03`–`0x04`, `0x06`–`0x07` | Not supported |

RX demux is `handle_ecpri_ethertype()` in `fhi_lib/lib/src/xran_main.c`.

## C-plane and U-plane at the DU

The DU is the C-plane source. The O-RU does the IFFT and FFT.

- **Downlink:** DU sends C-plane, then U-plane IQ for that symbol window.
- **Uplink:** DU sends UL C-plane so the O-RU knows which RBs and symbols to return, then receives U-plane IQ.
- **PRACH:** C-plane section type 3, filter index for formats A/B/C (B4 in this lab).

Section types the library actually uses (`xran_cp_api.h`):

| Section type | Use at this DU |
|---|---|
| 1 | Normal DL/UL channels |
| 3 | PRACH and mixed numerology |
| 0, 5, 6, 7 | Defined, not supported |

U-plane application header carries direction, payload version, `filterIndex`, `frameId`, subframe, slot, and symbol. Compression is in `udCompHdr` (`udCompMeth`, `udIqWidth`). The 100 MHz n79 profile uses **9-bit** IQ for data and **16-bit** for PRACH (`iq_width = 9`, `iq_width_prach = 16`).

## Timing

S-plane is not inside the eCPRI packets. PTP and SyncE stay on the E810 PF (`ice` / `ptp4l`). eCPRI stays on the VF. Symbol windows in `fhi_72.fh_config` for the 100 MHz n79 profile (`configs/gnb/002.gnb.sa.e2e.band79.100mhz.273.fhi72.4x4.conf`):

| Window | Value (µs) | Meaning |
|---|---|---|
| `T1a_cp_dl` | `(240, 450)` | DL C-plane send window |
| `T1a_cp_ul` | `(20, 350)` | UL C-plane send window |
| `T1a_up` | `(115, 325)` | DL U-plane send window |
| `Ta4` | `(75, 99)` | UL U-plane receive window |

Those windows are relative to the air slot and must match the O-RU.

## Where it lives

| Piece | Path |
|---|---|
| eCPRI header and message types | `sources/o-du-phy-oran_f_release_v1.9/fhi_lib/lib/api/xran_pkt.h` |
| C-plane section types | `fhi_lib/lib/api/xran_pkt_cp.h`, `xran_cp_api.h` |
| U-plane build | `fhi_lib/lib/src/xran_up_api.c`, `xran_tx_proc.c` |
| C-plane build | `fhi_lib/lib/src/xran_transport.c` |
| RX demux | `fhi_lib/lib/src/xran_main.c` (`handle_ecpri_ethertype`) |
| OAI ↔ xRAN | `sources/openairinterface5g-v26.w14/radio/fhi_72/oran-init.c`, `oaioran.c`, `oran_isolate.c` |
| Lab config | `configs/gnb/002.gnb.sa.e2e.band79.100mhz.273.fhi72.4x4.conf` (`fhi_72`) |
