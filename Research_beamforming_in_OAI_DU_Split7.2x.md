# Beamforming on the OAI DU, Split 7.2x

| Field | Value |
|---|---|
| Document ID | LATUAN-STD-BF-001 |
| Title | Beamforming on the OAI DU, Split 7.2x |
| Type | Study |
| Product | OAI DU, Split 7.2 |
| Location | `docs/LATUAN_beamforming_oai_study.md` |
| Version | 1.1 |
| Release date | 2026.10.29 |
| Status | Released as a study. Source is unchanged. |
| Classification | Internal |
| Related | `docs/LATUAN_phytest_tx_phase_design.md` (LATUAN-DES-TXPHASE-001) |
| Tag | None. This study does not patch source. Implementation uses `__PORTING_TM_MODE__` in the related design. |

## Author list

| Role | Name | Date |
|---|---|---|
| Author | LATUAN | 2026.10.29 |
| Reviewer | — | — |
| Approver | — | — |

## Release

| Revision | Release date | Author | Description |
|---|---|---|---|
| 1.0 | 2026.10.29 | LATUAN | Initial release in the controlled-document format. OAI beamforming support on Split 7.2, and whether a TX phase can be applied at the DU when the O-RU has no precoding matrix. |
| 1.1 | 2026.10.29 | LATUAN | English text. Technical findings unchanged. |

## Contents

1. Three concepts that stay separate
2. How far this OAI tree goes
3. The downlink path that actually runs
4. Trying a phase at the OAI DU when the RU has no precoding matrix
5. What to confirm on the live system before changing phase
6. Summary

---

This study answers one deployment question, then checks it against the OAI source in this tree (`sources/openairinterface5g-v26.w14`).

Where this study and LATUAN-DES-TXPHASE-001 differ on the insertion point, the design is the one to implement.

**Question:** The O-RU does not support a precoding matrix. Can the phase be adjusted at the OAI DU?

**Answer:** Yes, if the goal is to change the relative phase between IQ streams the DU has already built, and each eAxC is mapped 1:1 by the RU onto one TX chain with no extra weight. That phase is inside the U-plane IQ samples. The RU does not need the matrix \(W\), and it does not need Section Type 6.

This does not command a phase shifter inside the RFIC, and it is not a `beamId` on the C-plane. A TX chain that carries no IQ energy does not form a beam when a phase is applied to it.

The 4T4R configuration of this stack (`nb_tx = 4`, four eAxC, `pdsch_AntennaPorts_N1 = 2`, `pdsch_AntennaPorts_XP = 2`) has enough ports. The path that actually runs usually puts PDSCH on one antenna when PMI is 0 or when `independent_stream_mode` is on. A relative phase on RF appears only when the same waveform, or a weighted copy of it, is placed on more than one port.

---

## 1. Three concepts that stay separate

| Concept | Who decides | Who executes it on this stack | What the fronthaul carries |
|---|---|---|---|
| Beam management | MAC: pick a beam from SSB, UE measurements, or policy | Only when analog beamforming is on. The default `NO_BEAM_MODE` selects no beam | `beamId` in the C-plane, and only if the analog path is enabled |
| Digital precoding | MAC selects the PMI; PHY multiplies by \(W\) | OAI high-PHY, before the IFFT and before the eCPRI pack | \(W\) is not sent. The U-plane is already precoded IQ |
| Beamforming execution | Depends on the architecture | The RU or the RFIC, and only when that RU is configured to do it. OAI code does not assume the RU does | `beamId` or a weight, depending on RU capability |

A static beam is a weight table or a `beamId` configured in advance, then selected by index. Dynamic weight adaptation recomputes the complex coefficients from the channel. Picking one row of a 3GPP codebook is dynamic **selection** of a vector that was already generated. It is not an arbitrary matrix sent to the RU.

Section Type 6 in the O-RAN CUS plane is not "a packet that carries a dynamic \(W\)". In the FHI code of this tree, the C-plane field that is written is `nBeamIndex` (`beamId`), and only when the `beam_id` array is not −1.

---

## 2. How far this OAI tree goes

The comparison source is OAI v26.w14 in this repo, plus the phy-test branches already ported (`independent_stream_mode`, SSB replicate).

| Mechanism | State in the source | Effect when the RU has no precoding matrix |
|---|---|---|
| Type I codebook, PDSCH + DM-RS | **Present and running** | The DU multiplies \(W\) into the IQ. The RU radiates each eAxC |
| PMI = 0 (identity) | **The path that actually runs** | Layer \(k\) is copied to antenna \(k\). The other antennas are cleared |
| `identity_precoding_matrix` | Present, default `0` (does not force identity) | Set `1` to keep PMI at 0 |
| `independent_stream_mode` | Present on the phy-test branch | Forces PMI 0; layer 0 goes to one `stream_antenna`. Any other PMI hits `AssertFatal` |
| SSB / PBCH | Written to antenna 0 | Phy-test can `memcpy` that buffer onto the eAxC bits in `dl_tx_eaxc_mask`. Same phase. It does not steer a beam |
| PDCCH + PDCCH DM-RS | Only `txdataF[beam][0]` | No multi-port precoding |
| CSI-RS | Generated from the port configuration | `do_CSIRS = 0` on the TM 4x4 confs in use |
| Analog `beamId` to the C-plane | Code exists, **off** in `NO_BEAM_MODE` | `set_analog_beamforming` / `PRECONFIGURED_BEAM_IDX` require monolithic mode. Split 7.2 does not take this path |
| Digital beam table (DBT) weights at the FEP | **Does not run** | `nr_feptx()` calls `AssertFatal` if `num_dig_beams != 0` and analog BF is off |
| `nr_beam_precoding()` | The function exists and **has no caller** | It is not a live beam-control API |
| Weight-based beamforming sent to the RU | Absent | Matches an RU that does not accept a precoding matrix |
| UL digital combining at the RU | Absent | Each RX eAxC goes up to the DU; the DU estimates the channel |

Support level: this OAI DU is a **DU-side digital precoder for PDSCH**, plus an **analog `beamId` path that is unused on Split 7.2**. There is no digital beamforming executor of the form "receive a `beamId`, then multiply a weight table" in the OAI virtual RU, and there is no protocol that pushes a weight matrix down to the O-RU.

---

## 3. The downlink path that actually runs

```
MAC  get_pm_index()  →  pm_idx in the PDSCH PDU
        │
        ▼
PHY  nr_pdsch_symbol_processing()
        resource map (data + DM-RS share the layer buffer)
        do_txdataF()
            pm_idx == 0  →  memcpy layer → txdataF[ant]
            pm_idx != 0  →  nr_layer_precoder_simd()  (Q15 complex MAC)
        │
        ▼
RU thread  nr_feptx()
        analog_bf off and num_dig_beams == 0
        → fft_shift(txdataF → txdataF_BF)   // no weight multiply
        │
        ▼
FHI 7.2  oaioran.c
        each ant_id → one eAxC
        nBeamIndex is written only when beam_id != -1
        IQ is BFP-compressed into the U-plane
        │
        ▼
O-RU  map eAxC → TX chain → DAC → RFIC → PA → antenna
```

After `do_txdataF()`, the phase relation between antennas is already in the IQ. `nr_feptx()` does not change that phase. If the RU radiates each eAxC as it arrives, a VSA on each RF port measures the relative phase the DU wrote, minus the fixed error of that RF chain. Calibrate that error before turning the phase into an angle of arrival.

### 3.1 Where PDSCH multiplies the weights

`do_txdataF()` in `openair1/PHY/NR_TRANSPORT/nr_dlsch.c`:

- Reads `precodingAndBeamforming.prgs_list[].pm_idx`.
- `pm_idx == 0`: identity. Antennas below `nrOfLayers` receive that layer. The other antennas are `memset` to 0.
- `pm_idx != 0`: takes `gNB->gNB_config.pmi_list.pmi_pdu[pm_idx - 1]` and calls `nr_layer_precoder_simd()`.
- DM-RS and data share `txdataF_precoding` before this function, so a UE can still demodulate when \(W\) is applied to both. Do not rotate the data and leave the DM-RS unchanged.

`nr_layer_precoder_simd()` (`openair1/PHY/MODULATION/nr_modulation.c`) is a Q15 complex multiply:

\[
y_{\text{ant}}[k] = \sum_{\ell} x_{\ell}[k] \, w_{\ell,\text{ant}}
\]

with a 15-bit shift. The weights are `c16_t`, so any phase can be stored as \((\cos\phi, \sin\phi)\) in Q15, not only \(0^\circ/90^\circ/180^\circ/270^\circ\).

The codebook is built at cell configuration in `init_DL_MIMO_codebook()` (`openair2/LAYER2/NR_MAC_gNB/config.c`): Type I single-panel, a DFT beam from \(N_1\), \(N_2\), and the co-phasing angle \(\theta_n = e^{j\pi n/2}\). On the 4x4 conf, \(N_1 = 2\), \(N_2 = 1\), \(X_P = 2\), so there are 4 antenna ports. That is a 3GPP codebook, not the RU's angle-beam table.

`get_pm_index()` returns 0 for DCI 1_0, or when `identity_precoding_matrix = 1`, or when there is one antenna port. Otherwise the PMI comes from the UE CSI report. Phy-test has no real CSI. If the scheduler still uses DCI 1_1 with a PMI report of 0, the returned index is not identity. `independent_stream_mode` stops that case with `AssertFatal`.

### 3.2 SSB and PDCCH do not follow the PDSCH precoder

`nr_common_signal_procedures()` writes PSS, SSS, PBCH, and PBCH DM-RS into `txdataF[beam_nb][0]`.

The phy-test function `phytest_replicate_ssb_to_tx_antennas()` only `memcpy`s the four SSB symbols from antenna 0 onto the bits in `dl_tx_eaxc_mask`. Amplitude and phase are identical. That is the same wave on several ports, a phase vector of \(0^\circ\). It is not a steered beam.

`nr_dci.c` maps PDCCH into `txdataF[beam_nb][0]`. A phase rotation inside `do_txdataF()` does not touch PDCCH or SSB.

### 3.3 The FEP and the fronthaul add no beamforming

`nr_feptx()` in `openair1/SCHED_NR/nr_ru_procedures.c`:

- Analog BF copies `beam_id` from the gNB to the RU, then still only FFT-shifts the IQ.
- No digital beam (`num_dig_beams == 0`), or analog BF is on: copy and FFT-shift, no weight multiply.
- The remaining branch is `AssertFatal("This needs to be fixed by using appropriate beams from config")`.

`nr_beam_precoding()` in `openair1/PHY/MODULATION/nr_beamforming.c` multiplies `beam_weights[p][aa]` across the symbol. There is no call site in this NR tree. Do not treat that function as a live beamforming API.

`oaioran.c` sets `p_prbMapElm->nBeamIndex` from `ru->beam_id[]`. That array is allocated in the RU and filled with −1. When analog BF is off, the gNB does not allocate `common_vars->beam_id` (`phy_init_nr_gNB()` mallocs it only when the vendor extension is on). `beam_index_allocation()` returns 0 immediately if `beam_id == NULL`. On FHI, `beam_id == -1` means `nBeamIndex` is not written, except in the Liteon FR2 mode `RunSlotPrbMapBySymbolEnable`, which is not this 4T4R configuration. The C-plane therefore carries no meaningful `beamId`.

`set_analog_beamforming = PRECONFIGURED_BEAM_IDX` hits `AssertFatal` unless the mode is `NFAPI_MONOLITHIC`. A Split 7.2 DU does not start analog beam sweeping with that parameter.

The DBT (`dbt_file` / `read_dbt_from_config`) is parsed into the FAPI configuration. The FEP does not apply those weights. Setting `num_dig_beams > 0` on the current 7.2 path stops the process inside `nr_feptx()`.

### 3.4 Uplink

PUSCH, SRS, and PUCCH select `beam_nb` through the same `beam_index_allocation()`. With analog BF off, everything stays on beam 0. Per-antenna RX IQ sits in `rxdataF[beam][ant]`. There is no receive-vector multiply before the U-plane is compressed toward the DU. SRS feeds the UL channel estimate at the DU. The RU does not derive a UE angle by itself.

---

## 4. Trying a phase at the OAI DU when the RU has no precoding matrix

### 4.1 What can be done

Multiply each antenna stream by \(e^{j\phi_a}\) in the frequency domain, before `nr_feptx()` and before BFP compression:

\[
x'_a[k] = x_a[k] \, e^{j\phi_a}, \qquad e^{j90^\circ} = j \Rightarrow I+jQ \mapsto -Q+jI
\]

The RF measurement is meaningful only when:

1. The four DL eAxC (PC_ID `0x0000`–`0x0003` in the 4x4 conf) map onto four TX chains. The RU does not combine them and does not apply its own weight.
2. The same waveform, or the same weighted waveform, is present on at least two antennas. If only antenna 0 is non-zero, the phase of antennas 1–3 does not appear on the air.
3. Every RE the UE uses to demodulate that channel, data and DM-RS, carries the same \(\phi_a\).
4. The RU does not apply a second precoder. Applying \(W\) twice corrupts phase and power.
5. Relative phase is measured with a VSA on each port, or between ports that have been calibrated. The physical angle of arrival still depends on element spacing, frequency, and the fixed RF phase error. `beamId` does not encode that angle.

Example for four elements, \(d = \lambda/2\), \(\theta = 30^\circ\):

\[
\Delta\phi = -\frac{2\pi d}{\lambda}\sin\theta = -90^\circ
\]

\[
\mathbf{w} = \frac{1}{2}
\begin{bmatrix} 1 \\ -j \\ -1 \\ j \end{bmatrix}
=
\begin{bmatrix}
0.5+j0 \\
0-j0.5 \\
-0.5+j0 \\
0+j0.5
\end{bmatrix}
\]

The phases are \(0^\circ, -90^\circ, -180^\circ, -270^\circ\). This is an illustration, not the RU beam table.

### 4.2 Two methods, at different levels of readiness in the code

**Method A — use the PDSCH precoder that already exists.** The RU does not receive \(W\).

- Turn `independent_stream_mode` off. That path forbids a non-zero PMI.
- Leave `identity_precoding_matrix = 0`.
- One layer, one codeword.
- Pick a `pm_idx` that points at a 4-port codebook row already built in `init_DL_MIMO_codebook()`, or overwrite `pmi_pdu[].weights` with the Q15 phase vector above.
- `nr_layer_precoder_simd()` spreads that layer onto four antennas. DM-RS travels with it, so a single-layer UE can still track the channel, provided the UE sees the spatial combination (real antennas, or an RF combiner). On a per-port VSA, PDSCH amplitude appears on all four chains at the phase of \(w\).

Limit: SSB and PDCCH stay on antenna 0. The SSB spatial pattern does not change unless SSB is replicated and then rotated. The Type I codebook is not an analog phase shifter, and it does not track SRS unless the MAC changes the PMI from CSI.

**Method B — rotate the whole symbol after every channel has written `txdataF`.** This matches the experiment "does the RF port keep the phase offset".

The insertion described here is the start of `nr_feptx()`, before `fft_shift()`, on `gNB->common_vars.txdataF[bb][aa]`. One Q15 coefficient per antenna, applied to every RE of the symbols about to be sent. LATUAN-DES-TXPHASE-001 places the same multiply in `nr_feptx_tp()`, once per downlink slot, before `pushTpool`. Implement that design, not this paragraph.

SSB and PDCCH join the beam only if they are **replicated** from antenna 0 onto antennas 1..3 before the phase multiply. Otherwise only PDSCH carries energy on those ports, and only when PDSCH was already spread by method A or by a copy.

Do not edit IQ after BFP. Do not rotate PDSCH alone inside `do_txdataF()` if DM-RS is outside that loop. In the current code DM-RS shares the loop, so method A is safe for PDSCH. Method B is safe for every channel already present in `txdataF`.

### 4.3 What an OAI change cannot do

- Set a flag and expect the RU to apply a precoding matrix. The source does not send that matrix.
- Use `set_analog_beamforming` on an FHI 7.2 DU to move an RU phase shifter. The OAI analog path is monolithic, and `beamId` is an index, not an angle.
- Treat `nr_beam_precoding()` or the DBT as a running path. There is no caller, and the FEP asserts if the digital beam table is enabled.
- Derive the UE direction from SRS and have the RU rotate itself. SRS stops at the DU channel estimate.
- Judge a beam pattern from UE throughput alone. Measure the relative phase of each TX chain first, then the radiation pattern.

---

## 5. What to confirm on the live system before changing phase

1. **The four eAxC are really separate.** The TM 4x4 conf sets `nb_tx = nb_rx = 4` and PC_ID `0x0000`–`0x0003`. Capture the U-plane: four PC_IDs, and non-zero IQ on the ports that were replicated or spread by the precoder. A port that is all zeros has no phase to measure.
2. **The RU does not beamform again.** M-plane and vendor capability: no weight-based DL, and no `beamId` table that the RU multiplies on its own. If the RU still applies one default beam to every eAxC, the DU phase offset is added to the RU analog phase.
3. **The C-plane carries no weight.** Expect an ordinary section (Type 1) that describes symbol, PRB, and eAxC. On the default OAI path `nBeamIndex` is not set from `beam_id` (the value −1 is skipped).
4. **Which PHY path is running.** If the log or the conf has `independent_stream_mode = 1`, PDSCH is identity on one antenna. The codebook experiment (method A) must turn that mode off. `dl_tx_eaxc_mask` only selects the eAxC for the phy-test SSB copy. It does not create a phase offset.
5. **The measurement.** On the same symbol: power and relative phase of the four TX ports, and EVM per port. Change \(\phi\) and measure again. UE throughput is the later step, after DM-RS and data share the phase and the UE sits in the direction where the waves add.

---

## 6. Summary

- Static and dynamic describe **where the weights come from**. On this OAI, PDSCH weights come from the Type I codebook inside the DU, or from identity. The RU is not in the loop that computes \(W\).
- OAI **does** perform digital PDSCH precoding in `do_txdataF()` → `nr_layer_precoder_simd()`. The eAxC IQ is the result. An RU with no precoding matrix can still radiate those streams.
- OAI **does not** run digital beamforming from `beamId` or the DBT (`nr_feptx` asserts, and `nr_beam_precoding` is never called). Analog `beamId` **has code**, but it is off on Split 7.2 and it does not command an RU phase shifter.
- SSB and PDCCH default to one antenna. Phy-test only copies SSB at the same phase.
- A valid phase experiment spreads one signal onto the eAxC, multiplies by \(e^{j\phi_a}\) before the fronthaul, keeps DM-RS in phase with the data, and measures at the RF ports. That is digital precoding at the DU, not analog beam control of the RU.
