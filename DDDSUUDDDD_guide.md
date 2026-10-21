# Cell Configuration Check — n79, 100 MHz, SCS 30 kHz, TDD 5 ms

## 1. Cell Configuration

- **Band:** n79 (FR1, TDD)
- **SCS:** 30 kHz
- **Channel bandwidth:** 100 MHz
- **Number of PRBs:** 273
- **PCI:** 0

## 2. Frequency

Above 3 GHz, each NR-ARFCN step is 15 kHz, with reference ARFCN 600000 at 3000 MHz:

`F (MHz) = 3000 + 0.015 × (N − 600000)`

| Parameter | Value | Frequency |
|---|---:|---:|
| `absoluteFrequencyPointA` | 714724 | 4720.86 MHz |
| `absoluteFrequencySSB` | 717216 | 4758.24 MHz |
| GSCN | 8720 | Sync raster, 1.44 MHz step |
| Carrier center | — | 4770.00 MHz |
| Carrier edges | — | 4720.86–4819.14 MHz |

Occupied bandwidth is `273 × 12 × 30 kHz = 98.28 MHz`. The SSB lies inside the carrier. The test equipment and UE use the channel center, **4770 MHz**; **4758.24 MHz** is the SSB center.

## 3. SSB and CORESET0

- The SSB-to-Point-A distance is 2492 steps of 15 kHz.
- The lowest SSB PRB on the 30 kHz grid is **93**.
- `offsetToPointA = 186` (15 kHz PRBs).
- `k_SSB = 20`.
- **SSB Case C**, periodicity 10 ms, with only SSB index 0 enabled: slot 0, symbols 2–5. Slot 0 is a full downlink slot.
- `controlResourceSetZero = 4` (TS 38.213, Table 13-6): 48 RB, 1 symbol, PRBs 93–140, within the 273-PRB carrier.
- The initial BWP covers the full carrier: `locationAndBandwidth = 1099`.
- SSB index 7 cannot be used because it starts at symbol 8 of slot 3, which falls in the guard region of the special slot.

## 4. TDD Configuration — `DDDSUUDDDD`, 5 ms Period

At 30 kHz SCS, one slot is 0.5 ms. The two patterns add up to 5 ms and repeat twice in a 10 ms frame.

| Parameter | Pattern 1 | Pattern 2 |
|---|---:|---:|
| Period | 3 ms | 2 ms |
| Downlink slots | 3 | 4 |
| Uplink slots | 2 | 0 |
| DL symbols in special slot | 6 | 0 |
| UL symbols in special slot | 4 | 0 |

The special slot has `14 − 6 − 4 = 4` guard symbols.

The 10-slot order is:

`D D D S U U D D D D`

- Slots 4 and 5 are full uplink slots.
- Slot 3 is the special slot.
- RU TDD `pattern-id = 4` corresponds to this map.

## 5. PRACH

- `prach-ConfigurationIndex = 156` (TS 38.211, Table 6.3.3.2-3): format B4, once per frame, subframe 2, slot 5, symbol 0, duration 12 symbols.
- Slot 5 is uplink, so the 12 PRACH symbols fit within the 14-symbol slot.
- Index 159 falls in subframe 9, slot 19. Slot 19 is downlink in this TDD pattern, so index 159 is not used.
- The RU does not store a PRACH configuration index. The DU signals the index-156 occasion in the C-plane. The RU needs `pattern-id = 4`, the existing PRACH eAxC, and 16-bit PRACH IQ width.

## 6. Items to Confirm

1. **Frequency and cell:** Point A `714724`, SSB `717216`, GSCN `8720`, carrier center 4770 MHz, 273 PRBs, SCS 30 kHz, PCI 0.
2. **TDD:** `DDDSUUDDDD`, with the special slot configured as 6 DL + 4 guard + 4 UL symbols, matching RU `pattern-id = 4`.
3. **PRACH:** Configuration index 156, slot 5. Index 159 is not configured.
4. **SSB and CORESET0:** SSB index 0 is in slot 0. CORESET0 index 4 is within the 273-PRB carrier.
5. **Random access:** Confirm that PRACH Msg1 is received in slot 5 and that Msg2 through Msg4 complete.
