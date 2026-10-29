#!/usr/bin/env python3
"""DU beam control onto a 4x4 O-RU, Category A, split 7.2x.

Mirrors the lab profile in gNB_beamforming_control.md and the OAI path
init_DL_MIMO_codebook() -> nr_layer_precoder_simd() -> eAxC IQ, beamId 0.

What the program shows
  1. MAC picks pm_idx. pm_idx 0 is identity. pm_idx > 0 is one row of the
     TS 38.214 Type I single-panel codebook (N1=2, N2=1, XP=2), stored as Q15.
  2. DU L1 computes y[ant] = sum_layers W[layer][ant] * x[layer] per RE.
     That y is the frequency-domain sample of logical port 1000+ant.
  3. Fronthaul ships four eAxC flows (0x0000..0x0003), BFP-9, C-plane beamId 0.
  4. The RU does not own W. It binds eAxC k to antenna k, decompresses,
     IFFT-4096, adds the cyclic prefix, and sends the chain through the AFE.
  5. A second scene (lophy) shows the only RU beam control this DU can send:
     a beamId into a table that already lives in the RU. Weights are not on
     the wire.

Antenna index is the OAI / 38.214 order, which is what the precoder multiplies:

  ant 0  eAxC 0x0000  port 1000  polarization 0  column 0
  ant 1  eAxC 0x0001  port 1001  polarization 0  column 1
  ant 2  eAxC 0x0002  port 1002  polarization 1  column 0
  ant 3  eAxC 0x0003  port 1003  polarization 1  column 1

Run:
  python3 du_ru_beam_control.py
  python3 du_ru_beam_control.py --list-rank1
  python3 du_ru_beam_control.py --layers 1 --i11 2 --i2 1
  python3 du_ru_beam_control.py --scene analog --analog-beam 3
  python3 du_ru_beam_control.py --plot
"""

from __future__ import annotations

import argparse
import cmath
import math
import os
from dataclasses import dataclass

N1 = 2
N2 = 1
XP = 2
N_ANT = N1 * N2 * XP  # 4
O1 = 4
O2 = 1  # N2 == 1
N_FFT = 4096
SCS_HZ = 30_000
FS_HZ = N_FFT * SCS_HZ  # 122.88 MHz, same FSW as the PC805 uc2 path
CP_SAMPLES = 288  # normal CP at this FFT size; long symbols use 352
D_LAMBDA = 0.5
Q15 = 32767  # SHRT_MAX, convert_precoder_weight()
IQ_AMP = 8192  # layer sample amplitude, int16, same scale as txdataF

# Column phase of an analog beam the RU would already store.
# Keyed by the beamId the C-plane would carry. Not downloaded by this DU.
ANALOG_BEAM_DEG = {
    0: (0.0, 0.0),
    1: (0.0, 0.0),
    3: (0.0, -90.0),
    5: (0.0, 90.0),
    7: (0.0, 180.0),
}

PORT = (
    # ant, eaxc, logical port, polarization, column
    (0, 0x0000, 1000, 0, 0),
    (1, 0x0001, 1001, 0, 1),
    (2, 0x0002, 1002, 1, 0),
    (3, 0x0003, 1003, 1, 1),
)


@dataclass(frozen=True)
class Precoder:
    pm_idx: int
    layers: int
    # W[layer][ant] complex. Identity is exact. Codebook entries are the
    # float values before Q15 rounding, matching precoding_weigths_generation().
    w: tuple
    i11: int | None = None
    i12: int | None = None
    i13: int | None = None
    i2: int | None = None
    kind: str = "codebook"

    def q15(self):
        """Q15 weights as L1 stores them: round(32767 * W)."""
        out = []
        for layer in self.w:
            row = []
            for z in layer:
                row.append((c_round(Q15 * z.real), c_round(Q15 * z.imag)))
            out.append(tuple(row))
        return tuple(out)


def c_round(x: float) -> int:
    """C round(): half away from zero. Python round() is half to even."""
    if x >= 0:
        return int(math.floor(x + 0.5))
    return int(math.ceil(x - 0.5))


def sat16(v: int) -> int:
    if v > 32767:
        return 32767
    if v < -32768:
        return -32768
    return v


def get_k1_k2_count(layers: int) -> tuple[int, int]:
    """get_K1_K2() for N1=2, N2=1."""
    if layers == 1:
        return 1, 1
    if layers == 2:
        # N1 == 2 takes the K1=2 branch before the N2==1 / K1=4 branch.
        return 2, 1
    if layers in (3, 4):
        return N1, 1
    raise ValueError(f"layers {layers} not in 1..4")


def k1_k2_from_i13(layers: int, i13: int) -> tuple[int, int]:
    """get_k1_k2_indices() for N1=2, N2=1. Returns the loop indices, not degrees."""
    k1, k2 = 0, 0
    if layers == 2:
        k1 = i13
    elif layers in (3, 4):
        k1 = i13 + 1
    return k1, k2


def build_codebook() -> list[Precoder]:
    """Same loop order as precoding_weigths_generation() in config.c.

    pm_idx 0 is not in this list. Callers treat 0 as identity.
    Magnitude is sqrt(1/L) on every entry, which is what OAI stores.
    TS 38.214 normalizes by 1/sqrt(N1*N2*XP). The beam *direction* is the
    same; only the absolute scale differs. This sim follows OAI.
    """
    max_l = N1 * O1 + 4 * O1
    max_m = N2 * O2 + O2
    v = [
        [cmath.exp(1j * (2 * math.pi * nn * ll) / (N1 * O1)) for nn in range(N1)]
        for ll in range(max_l)
    ]
    u = [
        [cmath.exp(1j * (2 * math.pi * nn * mm) / (N2 * O2)) for nn in range(N2)]
        for mm in range(max_m)
    ]
    theta = [cmath.exp(1j * math.pi * nn / 2) for nn in range(4)]
    v_lm = []
    for ll in range(max_l):
        row_m = []
        for mm in range(max_m):
            spatial = []
            for nn1 in range(N1):
                for nn2 in range(N2):
                    spatial.append(v[ll][nn1] * u[mm][nn2])
            row_m.append(spatial)
        v_lm.append(row_m)

    book: list[Precoder] = []
    pm = 1
    for layers in range(1, 5):
        k1_count, k2_count = get_k1_k2_count(layers)
        i2_count = 4 if layers == 1 else 2
        scale = math.sqrt(1.0 / layers)
        for k2 in range(k2_count):
            for k1 in range(k1_count):
                for i12 in range(N2 * O2):
                    for i11 in range(N1 * O1):
                        for i2 in range(i2_count):
                            columns = []
                            for layer in range(layers):
                                llc = i11 + (k1 * O1 * (layer & 1))
                                mmc = i12 + (k2 * O2 * (layer & 1))
                                phase_sign = 1 if layer <= ((layers - 1) // 2) else -1
                                col = [scale * v_lm[llc][mmc][i] for i in range(N1 * N2)]
                                col += [
                                    scale * phase_sign * theta[i2] * v_lm[llc][mmc][i]
                                    for i in range(N1 * N2)
                                ]
                                columns.append(tuple(col))
                            book.append(
                                Precoder(
                                    pm_idx=pm,
                                    layers=layers,
                                    w=tuple(columns),
                                    i11=i11,
                                    i12=i12,
                                    i13=None,
                                    i2=i2,
                                    kind="codebook",
                                )
                            )
                            pm += 1
    return book


def identity(layers: int) -> Precoder:
    """pm_idx 0. Layer i is copied onto antenna i. Higher antennas stay 0.

    This is a memcpy in do_txdataF(), not a Q15 multiply.
    """
    columns = []
    for layer in range(layers):
        col = [0j] * N_ANT
        col[layer] = 1 + 0j
        columns.append(tuple(col))
    return Precoder(pm_idx=0, layers=layers, w=tuple(columns), kind="identity")


def pm_index_from_csi(layers: int, i11: int, i12: int, i13: int, i2: int) -> int:
    """get_pm_index() lay_index, plus 1, plus the matrices of the lower ranks."""
    sizes = []
    for L in range(1, 5):
        k1, k2 = get_k1_k2_count(L)
        i2_count = 4 if L == 1 else 2
        sizes.append(i2_count * N1 * O1 * N2 * O2 * k1 * k2)
    prev = sum(sizes[: layers - 1])
    k1, k2 = k1_k2_from_i13(layers, i13)
    max_i2 = 4 if layers == 1 else 2
    lay = (
        i2
        + i11 * max_i2
        + i12 * max_i2 * N1 * O1
        + k1 * max_i2 * N1 * O1 * N2 * O2
        + k2 * max_i2 * N1 * O1 * N2 * O2 * get_k1_k2_count(layers)[0]
    )
    return 1 + prev + lay


def qpsk_grid(n_re: int, layers: int) -> list[list[tuple[int, int]]]:
    """n_re of QPSK per layer. Returns [re][layer] = (I, Q)."""
    bits = [
        (1, 1),
        (1, -1),
        (-1, 1),
        (-1, -1),
        (1, -1),
        (-1, -1),
        (1, 1),
        (-1, 1),
        (1, 1),
        (-1, 1),
        (1, -1),
        (-1, -1),
    ]
    grid = []
    for re in range(n_re):
        layers_iq = []
        for layer in range(layers):
            bi, bq = bits[(re + 3 * layer) % len(bits)]
            layers_iq.append((bi * IQ_AMP, bq * IQ_AMP))
        grid.append(layers_iq)
    return grid


def precoding_one_re(p: Precoder, x: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """One RE, four antennas.

    Identity copies the layer and writes zeros, no shift.
    Codebook matches nr_layer_precoder_simd: Q15 complex MAC, arithmetic >> 15,
    saturate to int16. The SIMD conjugate is only there so madd becomes
    Re/Im of W*x. The mathematical product is W times x, not conj(W).
    """
    y = [(0, 0)] * N_ANT
    if p.kind == "identity":
        for ant in range(N_ANT):
            if ant < p.layers:
                y[ant] = x[ant]
            else:
                y[ant] = (0, 0)
        return y

    wq = p.q15()
    acc = [[0, 0] for _ in range(N_ANT)]
    for layer in range(p.layers):
        xr, xi = x[layer]
        for ant in range(N_ANT):
            wr, wi = wq[layer][ant]
            real = (xr * wr - xi * wi) >> 15
            imag = (xr * wi + xi * wr) >> 15
            acc[ant][0] = sat16(acc[ant][0] + real)
            acc[ant][1] = sat16(acc[ant][1] + imag)
    return [(a[0], a[1]) for a in acc]


def bfp_compress(samples: list[tuple[int, int]], iq_width: int = 9):
    """Teaching model of O-RAN block floating point, one PRB (12 RE).

    Shared exponent, signed mantissa of iq_width bits. The xRAN compressor
    has its own rounding; this shows the RU step, not a bit-exact frame.
    """
    peak = 0
    for i, q in samples:
        peak = max(peak, abs(i), abs(q))
    mag_bits = iq_width - 1
    exp = max(0, peak.bit_length() - mag_bits)
    mant = []
    for i, q in samples:
        mant.append((i >> exp, q >> exp))
    return exp, mant


def bfp_decompress(exp: int, mant: list[tuple[int, int]]) -> list[tuple[int, int]]:
    return [(i << exp, q << exp) for i, q in mant]


def analog_gains(beam_id: int) -> list[complex]:
    """Per-antenna gain stored in the RU for this beamId.

    Both polarizations of a column share the column phase. beamId 0 is the
    lab value: every gain is 1, so the air signal is exactly the DU IQ.
    """
    if beam_id not in ANALOG_BEAM_DEG:
        raise KeyError(f"beamId {beam_id} is not in the example RU table {sorted(ANALOG_BEAM_DEG)}")
    col = ANALOG_BEAM_DEG[beam_id]
    gains = [0j] * N_ANT
    for ant, _eaxc, _port, _pol, n1 in PORT:
        gains[ant] = cmath.exp(1j * math.radians(col[n1]))
    return gains


def apply_analog(iq: list[tuple[int, int]], gains: list[complex]) -> list[tuple[int, int]]:
    """What an RU beam table does to already-precoded FD IQ. Diagonal only."""
    out = []
    for (i, q), g in zip(iq, gains):
        z = complex(i, q) * g
        out.append((sat16(c_round(z.real)), sat16(c_round(z.imag))))
    return out


def pattern_power(weights: list[complex], az_deg: float) -> float:
    """|AF|^2 summed over the two polarizations. az=0 is broadside.

    Element n1 sits at n1 * 0.5 λ. Polarizations do not add in voltage.
    """
    s = math.sin(math.radians(az_deg))
    total = 0.0
    for pol in (0, 1):
        field = 0j
        for n1 in range(N1):
            ant = pol * N1 + n1
            field += weights[ant] * cmath.exp(1j * 2 * math.pi * n1 * D_LAMBDA * s)
        total += abs(field) ** 2
    return total


def peak_azimuth(weights: list[complex]) -> tuple[float, float]:
    best_az, best_p = 0.0, -1.0
    az = -90.0
    while az <= 90.0 + 1e-9:
        p = pattern_power(weights, az)
        if p > best_p:
            best_az, best_p = az, p
        az += 0.5
    return best_az, best_p


def layer_weights(p: Precoder, layer: int) -> list[complex]:
    return [p.w[layer][ant] for ant in range(N_ANT)]


def combined_weights(p: Precoder, x: list[tuple[int, int]]) -> list[complex]:
    """Float picture of one RE: y = W x, using the unquantized codebook."""
    y = [0j] * N_ANT
    for layer in range(p.layers):
        xs = complex(x[layer][0], x[layer][1])
        for ant in range(N_ANT):
            y[ant] += p.w[layer][ant] * xs
    return y


def fmt_c(z: complex) -> str:
    sign = "+" if z.imag >= 0 else "-"
    return f"{z.real:8.4f}{sign}{abs(z.imag):7.4f}j"


def fmt_iq(iq: tuple[int, int]) -> str:
    return f"({iq[0]:7d},{iq[1]:7d})"


def phase_deg(i: int, q: int) -> str:
    if i == 0 and q == 0:
        return "  silent"
    return f"{math.degrees(math.atan2(q, i)):7.1f}°"


def db_or_mute(p: float, peak: float) -> float:
    if p <= 0 or peak <= 0:
        return -80.0
    return 10.0 * math.log10(p / peak)


def ascii_cut(weights: list[complex], title: str) -> str:
    azs = list(range(-90, 91, 5))
    powers = [pattern_power(weights, az) for az in azs]
    peak = max(powers) if powers else 1.0
    lines = [title]
    for az, p in zip(azs, powers):
        db = db_or_mute(p, peak)
        if db < -30:
            bar = ""
        else:
            n = int(round((db + 30) / 30 * 40))
            bar = "#" * max(n, 0)
        lines.append(f"  {az:4d}° {db:6.1f} dB |{bar}")
    peak_az, _ = peak_azimuth(weights)
    lines.append(f"  peak {peak_az:6.1f}°    (0° is broadside, d = 0.5 λ)")
    return "\n".join(lines)


def td_samples(fd_by_ant: list[list[tuple[int, int]]], n_out: int = 8) -> list[list[complex]]:
    """First n_out samples of a 4096-point IFFT. Only the occupied bins are summed.

    Bins 0..n_re-1 stand in for 12 subcarriers of one PRB. phase_compensation
    in this profile is 0, so no extra tone rotation is applied.
    """
    n_re = len(fd_by_ant[0])
    out = []
    for ant in range(N_ANT):
        series = []
        for n in range(n_out):
            acc = 0j
            for k in range(n_re):
                i, q = fd_by_ant[ant][k]
                acc += complex(i, q) * cmath.exp(2j * math.pi * k * n / N_FFT)
            series.append(acc / N_FFT)
        out.append(series)
    return out


def print_matrix(p: Precoder) -> None:
    print(f"W rows are layers, columns are antennas. kind={p.kind} pm_idx={p.pm_idx} layers={p.layers}")
    if p.i11 is not None:
        print(f"CSI indices stored with this row: i11={p.i11} i12={p.i12} i2={p.i2}")
    print("        ant0 pol0 col0    ant1 pol0 col1    ant2 pol1 col0    ant3 pol1 col1")
    for layer in range(p.layers):
        cells = "  ".join(fmt_c(p.w[layer][ant]) for ant in range(N_ANT))
        print(f"  L{layer}  {cells}")
    if p.kind == "codebook":
        print("  Q15 (round to int16, the value L1 multiplies):")
        for layer, row in enumerate(p.q15()):
            cells = "  ".join(f"({wr:7d},{wi:7d})" for wr, wi in row)
            print(f"  L{layer}  {cells}")


def print_antenna_table(iq: list[tuple[int, int]], heading: str) -> None:
    print(heading)
    print(f"  {'ant':<4} {'eAxC':<8} {'port':<6} {'pol':<4} {'col':<4} {'FD IQ':<20} {'|IQ|':>8} {'phase':>10}")
    for ant, eaxc, port, pol, col in PORT:
        i, q = iq[ant]
        mag = math.hypot(i, q)
        print(
            f"  {ant:<4} 0x{eaxc:04x}  {port:<6} {pol:<4} {col:<4} {fmt_iq((i, q)):<20} {mag:8.1f} {phase_deg(i, q):>10}"
        )


def print_cplane(beam_id: int, n_re: int) -> None:
    print("C-plane section type 1 (one section, the whole carrier in the lab map):")
    print(f"  nRBStart=0  nRBSize=273  iqWidth=9  compMethod=BFP  beamId={beam_id}")
    print(f"  this demo occupies {n_re} RE of one symbol; the RU still keys the chain by ruPort, not by layer")
    for ant, eaxc, port, _pol, _col in PORT:
        print(f"  eAxC 0x{eaxc:04x}  ruPort={ant}  logical port {port}  -> TX chain {ant}")


def print_ru_steps(beam_id: int, decompressed: list[list[tuple[int, int]]]) -> None:
    print("RU Category A, per symbol, after the section is accepted:")
    print("  1. Bind eAxC ruPort k to TX antenna k for the life of the cell. No port remap.")
    print("  2. Decompress BFP-9. PRACH would be a different flow at iq_width 16.")
    print("  3. IFFT 4096 (273*12=3276 occupied subcarriers), insert CP, phase_compensation=0.")
    print(f"     Fs={FS_HZ/1e6:.2f} MHz, normal CP={CP_SAMPLES} samples, long CP=352.")
    print("  4. Resample is already at FSW on this FFT size. JESD to the AFE7769D.")
    print("  5. RFIC: NCO, CFR, DPD, DAC, TX LO. Discrete PA. No precoder, no weight section.")
    if beam_id == 0:
        print("  6. beamId 0. This profile has no beam table lookup. AFE gain is not steered.")
    else:
        print(f"  6. beamId {beam_id} selects a row already in the RU. IQ is still not a weight.")
    td = td_samples(decompressed, n_out=4)
    print("  First 4 time-domain samples after the IFFT (teaching bins 0..n_re-1):")
    for ant, _eaxc, port, _pol, _col in PORT:
        cells = "  ".join(fmt_c(z) for z in td[ant])
        print(f"    ant{ant} port {port}: {cells}")
    print("  A rank-1 grant makes these four waveforms the same shape, scaled by W[ant].")
    print("  Identity with two layers does not: ant0 and ant1 carry independent symbols.")


def scene_identity() -> None:
    print("=" * 78)
    print("Scene A. Lab digital control, pm_idx = 0, two layers (DCI 1_0 / identity)")
    print("=" * 78)
    p = identity(2)
    grid = qpsk_grid(12, p.layers)
    print("DU: CSI is not applied. get_pm_index() returns 0. L1 copies layer i onto antenna i.")
    print_matrix(p)
    print()
    print_antenna_table(precoding_one_re(p, grid[0]), "U-plane, RE 0, after the DU precoder (this is what each antenna radiates in frequency):")
    fd = [precoding_one_re(p, x) for x in grid]
    by_ant = [[fd[re][ant] for re in range(12)] for ant in range(N_ANT)]
    exp, mant = bfp_compress(by_ant[0])
    back = bfp_decompress(exp, mant)
    print()
    print(f"BFP-9 on eAxC 0, 12 RE, shared exponent={exp}. RU restores by << {exp}.")
    print(f"  DU int16 RE0 {fmt_iq(by_ant[0][0])}   mantissa {fmt_iq(mant[0])}   after decompress {fmt_iq(back[0])}")
    print("  ant2 and ant3 are exact zeros on the wire. The RU is not told a rank. It plays silence.")
    print()
    print_cplane(0, 12)
    print()
    print_ru_steps(0, by_ant)
    print()
    print("There is no steered beam. Two elements are on, two are muted, and the two")
    print("active ports carry different layers, so the array factor moves with the data.")
    print()


def describe_codebook(p: Precoder, grid_re0: list[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    print_matrix(p)
    for layer in range(p.layers):
        peak_az, _ = peak_azimuth(layer_weights(p, layer))
        print(f"  layer {layer} alone would peak at {peak_az:6.1f}°")
    iq = precoding_one_re(p, grid_re0)
    print()
    print_antenna_table(iq, "U-plane RE 0 after Q15 precoding (antenna port output in frequency):")
    float_y = combined_weights(p, grid_re0)
    print("  same RE from the float matrix, before Q15, relative phase vs ant0:")
    ref = float_y[0]
    for ant in range(N_ANT):
        if abs(float_y[ant]) < 1e-9 or abs(ref) < 1e-9:
            rel = "silent"
        else:
            rel = f"{math.degrees(cmath.phase(float_y[ant] / ref)):7.1f}°"
        print(f"    ant{ant}  {fmt_c(float_y[ant])}   phase-ant0 {rel}")
    return iq


def scene_codebook(p: Precoder) -> None:
    print("=" * 78)
    print("Scene B. Lab digital control, codebook pm_idx > 0. beamId stays 0.")
    print("=" * 78)
    print(
        f"UE CSI -> get_pm_index() = {p.pm_idx}   "
        f"(i11={p.i11} i12={p.i12} i2={p.i2} layers={p.layers})"
    )
    print("One PRG covers the grant, so this single W is used on every RE of the PDSCH.")
    print("Changing pm_idx changes W inside the DU. The RU binding eAxC -> antenna does not change.")
    print()
    grid = qpsk_grid(12, p.layers)
    describe_codebook(p, grid[0])
    fd = [precoding_one_re(p, x) for x in grid]
    by_ant = [[fd[re][ant] for re in range(12)] for ant in range(N_ANT)]
    print()
    print_cplane(0, 12)
    print()
    print_ru_steps(0, by_ant)
    print()
    if p.layers == 1:
        direction = [complex(iq[0], iq[1]) for iq in fd[0]]
        print(ascii_cut(direction, "Azimuth cut of RE 0 (both polarizations, power sum):"))
        print()
        print("i2 is the co-phasing between polarization 0 and 1. It does not move this")
        print("azimuth peak. i11 = 0..4 follows sin(az) = -i11/4. i11 = 5..7 continues")
        print("the same DFT past endfire and the peak comes back on the other side.")
    else:
        print("Rank > 1: each layer has its own column of W. The sample on an antenna is the")
        print("sum of the layers. The cut below is that sum for RE 0, so it depends on the")
        print("QPSK symbols as well as on W.")
        direction = [complex(iq[0], iq[1]) for iq in fd[0]]
        print(ascii_cut(direction, "Azimuth cut of the combined RE 0:"))
    print()


def scene_analog(base: Precoder, beam_id: int) -> None:
    print("=" * 78)
    print("Scene C. Contrast only: set_analog_beamforming = lophy. Not the 4x4 lab.")
    print("=" * 78)
    print("The DU still precodes. It does not send amplitudes or phases.")
    print("FAPI beam_idx has bit 15 set. L1 strips that bit and writes nBeamIndex.")
    print(f"C-plane beamId={beam_id} on every antenna (beams_per_period=1).")
    print("The RU multiplies the stored row. Category B weight sections are not built.")
    print()
    grid = qpsk_grid(12, base.layers)
    du_iq = precoding_one_re(base, grid[0])
    gains = analog_gains(beam_id)
    ru_iq = apply_analog(du_iq, gains)
    print_antenna_table(du_iq, "Leaving the DU (U-plane), beam not applied yet:")
    print()
    print("RU beam-table gains (magnitude 1):")
    for ant, phase in enumerate(gains):
        print(f"  ant{ant}  {fmt_c(phase)}")
    print()
    print_antenna_table(ru_iq, f"Leaving the antenna ports after beamId {beam_id}:")
    print()
    print_cplane(beam_id, 12)
    fd = []
    for x in grid:
        fd.append(apply_analog(precoding_one_re(base, x), gains))
    by_ant = [[fd[re][ant] for re in range(12)] for ant in range(N_ANT)]
    print()
    print_ru_steps(beam_id, by_ant)
    print()
    du_w = [complex(*iq) for iq in du_iq]
    ru_w = [complex(*iq) for iq in ru_iq]
    print(ascii_cut(du_w, "Azimuth if the RU ignored beamId (lab behaviour):"))
    print()
    print(ascii_cut(ru_w, f"Azimuth after the RU applies beamId {beam_id}:"))
    print()


def list_rank1(book: list[Precoder]) -> None:
    print("Rank-1 codebook. pm_idx = 1 + i2 + 4*i11. Peak uses d = 0.5 λ, pol power sum.")
    print(f"{'pm':>4} {'i11':>4} {'i2':>4} {'pol1/pol0':>10} {'peak':>8}")
    for p in book:
        if p.layers != 1:
            break
        pol_phase = math.degrees(cmath.phase(p.w[0][2] / p.w[0][0]))
        peak_az, _ = peak_azimuth(layer_weights(p, 0))
        print(f"{p.pm_idx:4d} {p.i11:4d} {p.i2:4d} {pol_phase:9.1f}° {peak_az:7.1f}°")
    n = [sum(1 for p in book if p.layers == L) for L in (1, 2, 3, 4)]
    print(f"matrix counts L1..L4 = {n}, total {sum(n)}. Identity is pm_idx 0 and is not in this list.")


def save_plot(book: list[Precoder], path: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    azs = [a / 2 for a in range(-180, 181)]
    fig, ax = plt.subplots(figsize=(8.0, 4.4))
    for i11, style in ((0, "-"), (2, "--"), (4, ":")):
        pm = pm_index_from_csi(1, i11, 0, 0, 0)
        w = layer_weights(book[pm - 1], 0)
        powers = [pattern_power(w, az) for az in azs]
        peak = max(powers)
        db = [db_or_mute(p, peak) for p in powers]
        ax.plot(azs, db, style, label=f"i11={i11}  pm_idx={pm}")
    ax.set_ylim(-30, 1)
    ax.set_xlim(-90, 90)
    ax.set_xlabel("azimuth (deg), 0 = broadside")
    ax.set_ylabel("power (dB, peak of each curve = 0)")
    ax.set_title("DU codebook, rank 1, N1=2, d=0.5λ  (RU does not form this)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    print(f"wrote {path}")


def self_check(book: list[Precoder]) -> None:
    counts = [sum(1 for p in book if p.layers == L) for L in (1, 2, 3, 4)]
    if counts != [32, 32, 32, 32]:
        raise RuntimeError(f"unexpected codebook sizes {counts}")
    if [p.pm_idx for p in book] != list(range(1, 129)):
        raise RuntimeError("pm_idx is not 1..128")
    # i11=0 is broadside. i11=2 steers to arcsin(-0.5) = -30°.
    for i11, expect in ((0, 0.0), (2, math.degrees(math.asin(-0.5)))):
        pm = pm_index_from_csi(1, i11, 0, 0, 0)
        peak, _ = peak_azimuth(layer_weights(book[pm - 1], 0))
        if abs(peak - expect) > 0.6:
            raise RuntimeError(f"i11={i11} peaked at {peak}, expected {expect}")
    p = book[pm_index_from_csi(1, 0, 0, 0, 0) - 1]
    x = [(IQ_AMP, 0)]
    y = precoding_one_re(p, x)
    # W entry 1.0 -> Q15 32767, so 8192*32767>>15 = 8191 on every antenna, phase 0.
    for ant in range(N_ANT):
        if y[ant] != (8191, 0):
            raise RuntimeError(f"Q15 broadside ant{ant} = {y[ant]}")
    ident = precoding_one_re(identity(2), [(100, -50), (7, 9)])
    if ident != [(100, -50), (7, 9), (0, 0), (0, 0)]:
        raise RuntimeError(f"identity copy failed: {ident}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scene", choices=("all", "identity", "codebook", "analog"), default="all")
    parser.add_argument("--layers", type=int, default=1, choices=(1, 2, 3, 4))
    parser.add_argument("--i11", type=int, default=2, help="horizontal beam index, 0..7")
    parser.add_argument("--i12", type=int, default=0, help="vertical index, only 0 when N2=1")
    parser.add_argument("--i13", type=int, default=0, help="used for rank >= 2")
    parser.add_argument("--i2", type=int, default=0, help="co-phasing, 0..3 for rank 1, 0..1 otherwise")
    parser.add_argument("--pm-idx", type=int, default=None, help="skip CSI indices and use this matrix")
    parser.add_argument("--analog-beam", type=int, default=3, choices=sorted(ANALOG_BEAM_DEG))
    parser.add_argument("--list-rank1", action="store_true")
    parser.add_argument("--plot", action="store_true", help="write pattern.png next to this file")
    args = parser.parse_args()

    book = build_codebook()
    self_check(book)

    if args.list_rank1:
        list_rank1(book)
        return

    if args.pm_idx is not None:
        if not 1 <= args.pm_idx <= len(book):
            raise SystemExit(f"--pm-idx must be 1..{len(book)} (0 is identity; use --scene identity)")
        chosen = book[args.pm_idx - 1]
    else:
        if args.i12 != 0:
            raise SystemExit("N2=1 so i12 must be 0")
        i2_max = 4 if args.layers == 1 else 2
        if not 0 <= args.i11 < N1 * O1:
            raise SystemExit(f"i11 must be 0..{N1 * O1 - 1}")
        if not 0 <= args.i2 < i2_max:
            raise SystemExit(f"i2 must be 0..{i2_max - 1} for {args.layers} layer(s)")
        pm = pm_index_from_csi(args.layers, args.i11, args.i12, args.i13, args.i2)
        if not 1 <= pm <= len(book) or book[pm - 1].layers != args.layers:
            raise SystemExit(
                f"CSI (layers={args.layers} i11={args.i11} i13={args.i13} i2={args.i2}) "
                f"does not land on a rank-{args.layers} matrix (pm_idx {pm})"
            )
        chosen = book[pm - 1]

    print("4x4 O-RU, n79, 100 MHz, 273 PRB, Category A, do_precoding = 0 on the RU.")
    print("Beam control in this lab is the IQ. The DU multiplies W(pm_idx). The RU transmits it.")
    print()

    if args.scene in ("all", "identity"):
        scene_identity()
    if args.scene in ("all", "codebook"):
        scene_codebook(chosen)
    if args.scene in ("all", "analog"):
        scene_analog(chosen, args.analog_beam)

    if args.plot:
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pattern.png")
        save_plot(book, out)


if __name__ == "__main__":
    main()
