# Nghiên cứu beamforming trên OAI DU Split 7.2x

| Field | Value |
|---|---|
| Document ID | LATUAN-STD-BF-001 |
| Title | Nghiên cứu beamforming trên OAI DU Split 7.2x |
| Type | Study |
| Product | OAI DU, Split 7.2 |
| Location | `docs/LATUAN_beamforming_oai_study.md` |
| Version | 1.0 |
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

## Contents

1. Ba khái niệm không được gộp làm một
2. OAI hiện hỗ trợ đến đâu
3. Luồng DL thực tế
4. Thử phase tại OAI khi RU không có precoding matrix
5. Việc nên xác nhận trên hệ đang chạy trước khi sửa pha
6. Tóm tắt để trình bày

---

Tài liệu này trả lời một câu hỏi triển khai cụ thể, rồi đối chiếu với source OAI trong cây này (`sources/openairinterface5g-v26.w14`).

Where this study and LATUAN-DES-TXPHASE-001 differ on the insertion point, the design is the one to implement.

**Câu hỏi:** O-RU chưa hỗ trợ precoding matrix. Có thử điều chỉnh pha tại OAI DU được không?

**Trả lời:** Được, nếu mục tiêu là đổi pha tương đối giữa các luồng IQ mà DU đã tạo, và mỗi luồng eAxC được RU ánh xạ 1-1 sang một TX chain mà không nhân thêm trọng số. Pha đó nằm trong mẫu IQ của U-plane. RU không cần nhận ma trận \(W\), và không cần Section Type 6.

Việc này **không** điều khiển phase shifter bên trong RFIC, và **không** tương đương beamId trên C-plane. Nếu một nhánh TX không có năng lượng IQ, nhân pha trên nhánh đó không tạo ra beam.

Cấu hình 4T4R của stack này (`nb_tx = 4`, bốn eAxC, `pdsch_AntennaPorts_N1 = 2`, `pdsch_AntennaPorts_XP = 2`) đủ điều kiện về số đường. Đường chạy mặc định hiện tại lại thường chỉ đổ PDSCH lên một anten khi PMI = 0 hoặc khi `independent_stream_mode` bật. Muốn thấy lệch pha trên RF phải chủ động trải cùng một tín hiệu (hoặc bản có trọng số) lên nhiều cổng.

---

## 1. Ba khái niệm không được gộp làm một

| Khái niệm | Ai quyết định | Ai thực thi trên stack này | Dữ liệu trên fronthaul |
|---|---|---|---|
| Beam management | MAC: chọn beam theo SSB / đo UE / policy | Chỉ khi bật analog beamforming. Mặc định `NO_BEAM_MODE` không chọn beam | `beamId` trong C-plane, nếu đường analog được bật |
| Digital precoding | MAC chọn PMI; PHY nhân \(W\) | OAI High-PHY, trước IFFT và trước khi đóng gói eCPRI | Không gửi \(W\). U-plane đã là IQ sau precoding |
| Beamforming execution | Tùy kiến trúc | RU / RFIC chỉ khi RU được cấu hình làm việc đó. Code OAI không giả định RU làm | beamId hoặc weight, tùy capability RU |

Static beam là bảng trọng số hoặc beamId đã cấu hình trước, rồi chọn chỉ số. Dynamic weight adaptation là tính lại hệ số phức theo kênh. Chọn một hàng trong codebook 3GPP là dynamic **selection** của một vector đã sinh sẵn, không phải gửi ma trận tùy ý sang RU.

Section Type 6 trong O-RAN CUS không phải “gói chứa \(W\) động”. Trên code FHI của cây này, trường được ghi ra C-plane là `nBeamIndex` (beamId), và chỉ khi mảng `beam_id` khác −1.

---

## 2. OAI hiện hỗ trợ đến đâu

Nguồn đối chiếu là OAI v26.w14 trong repo, cộng các nhánh phy-test đã port (`independent_stream_mode`, replicate SSB).

| Cơ chế | Trạng thái trong source | Hệ quả với RU không có precoding matrix |
|---|---|---|
| Codebook Type I, PDSCH + DM-RS | **Có, chạy được** | DU nhân \(W\) vào IQ. RU chỉ phát từng eAxC |
| PMI = 0 (identity) | **Đường mặc định thực tế** | Layer \(k\) copy sang anten \(k\). Anten còn lại bị xóa 0 |
| `identity_precoding_matrix` | Có, default `0` (không ép identity) | Đặt `1` để luôn PMI = 0 |
| `independent_stream_mode` | Có trong nhánh phy-test | Ép PMI = 0; layer 0 vào đúng một `stream_antenna`. PMI khác 0 thì `AssertFatal` |
| SSB / PBCH | Ghi vào anten 0 | Phy-test có thể `memcpy` cùng buffer sang các eAxC trong `dl_tx_eaxc_mask`. Cùng pha, không lái beam |
| PDCCH + DM-RS PDCCH | Chỉ `txdataF[beam][0]` | Không precoding đa cổng |
| CSI-RS | Sinh theo cấu hình cổng | `do_CSIRS = 0` trên các conf TM 4x4 hiện dùng |
| Analog beamId → C-plane | Code có, **tắt** khi `NO_BEAM_MODE` | `set_analog_beamforming` / `PRECONFIGURED_BEAM_IDX` yêu cầu monolithic. Split 7.2 không đi đường này |
| Digital beam table (DBT) áp weight tại FEP | **Không chạy** | `nr_feptx()` gọi `AssertFatal` nếu `num_dig_beams != 0` và không analog BF |
| `nr_beam_precoding()` | Hàm có, **không có caller** | Không phải API điều khiển beam |
| Weight-based beamforming gửi sang RU | Không có | Đúng với RU không nhận precoding matrix |
| UL digital combining tại RU | Không | Mỗi eAxC RX đi lên DU; DU ước lượng kênh |

Kết luận mức hỗ trợ: OAI DU này là **DU-side digital precoder cho PDSCH**, cộng một đường **beamId analog chưa dùng trên Split 7.2**. Không có bộ thực thi beamforming số kiểu “nhận beamId rồi nhân bảng weight” trên RU ảo của OAI, và không có giao thức đẩy ma trận trọng số xuống O-RU.

---

## 3. Luồng DL thực tế

```
MAC  get_pm_index()  →  pm_idx trong PDSCH PDU
        │
        ▼
PHY  nr_pdsch_symbol_processing()
        resource map (data + DM-RS cùng buffer layer)
        do_txdataF()
            pm_idx == 0  →  memcpy layer → txdataF[ant]
            pm_idx != 0  →  nr_layer_precoder_simd()  (Q15 complex MAC)
        │
        ▼
RU thread  nr_feptx()
        analog_bf tắt và num_dig_beams == 0
        → fft_shift(txdataF → txdataF_BF)   // không nhân weight
        │
        ▼
FHI 7.2  oaioran.c
        mỗi ant_id → một eAxC
        nBeamIndex chỉ ghi khi beam_id != -1
        IQ nén BFP rồi vào U-plane
        │
        ▼
O-RU  map eAxC → TX chain → DAC → RFIC → PA → anten
```

Điểm then chốt: sau `do_txdataF()`, quan hệ pha giữa các anten **đã nằm trong IQ**. `nr_feptx()` không sửa pha. Nếu RU phát thẳng từng eAxC, VSA trên từng cổng RF đo đúng pha tương đối mà DU đã đặt, trừ sai lệch cố định của từng đường RF (cần hiệu chuẩn nếu muốn đổi pha thành góc tới).

### 3.1 Chỗ PDSCH nhân trọng số

`do_txdataF()` trong `openair1/PHY/NR_TRANSPORT/nr_dlsch.c`:

- Đọc `precodingAndBeamforming.prgs_list[].pm_idx`.
- `pm_idx == 0`: identity. Anten `< nrOfLayers` nhận đúng layer; anten còn lại `memset 0`.
- `pm_idx != 0`: lấy `gNB->gNB_config.pmi_list.pmi_pdu[pm_idx - 1]` và gọi `nr_layer_precoder_simd()`.
- DM-RS và data đi cùng `txdataF_precoding` trước khi vào hàm này, nên UE vẫn giải điều chế được nếu \(W\) áp cho cả hai. Không được xoay pha riêng data mà để DM-RS nguyên.

`nr_layer_precoder_simd()` (`openair1/PHY/MODULATION/nr_modulation.c`) nhân số phức Q15:

\[
y_{\text{ant}}[k] = \sum_{\ell} x_{\ell}[k] \, w_{\ell,\text{ant}}
\]

với dịch 15 bit. Trọng số là `c16_t`, nên pha bất kỳ biểu diễn được bằng \((\cos\phi, \sin\phi)\) scale Q15, không chỉ \(0^\circ/90^\circ/180^\circ/270^\circ\).

Codebook được sinh lúc cấu hình cell trong `init_DL_MIMO_codebook()` (`openair2/LAYER2/NR_MAC_gNB/config.c`): Type I single-panel, DFT beam theo \(N_1, N_2\) và góc đồng pha \(\theta_n = e^{j\pi n/2}\). Với conf 4x4, \(N_1 = 2\), \(N_2 = 1\), \(X_P = 2\) → 4 antenna port. Đó là codebook 3GPP, không phải bảng beam góc của RU.

`get_pm_index()` trả 0 khi DCI 1_0, hoặc `identity_precoding_matrix = 1`, hoặc một antenna port. Ngược lại PMI lấy từ CSI report của UE. Phy-test không có CSI thật: nếu scheduler vẫn đi DCI 1_1 với PMI report bằng 0, index trả về không phải identity. `independent_stream_mode` chặn trường hợp đó bằng `AssertFatal`.

### 3.2 SSB và PDCCH không đi cùng precoder PDSCH

`nr_common_signal_procedures()` ghi PSS, SSS, PBCH, PBCH-DMRS vào `txdataF[beam_nb][0]`.

Nhánh phy-test `phytest_replicate_ssb_to_tx_antennas()` chỉ `memcpy` bốn symbol SSB từ anten 0 sang các bit trong `dl_tx_eaxc_mask`. Biên độ và pha giống hệt nhau. Đó là phát cùng sóng trên nhiều cổng, tương đương vector pha \(0^\circ\), chưa phải beam lái.

`nr_dci.c` map PDCCH vào `txdataF[beam_nb][0]`. Xoay pha trong `do_txdataF()` không đụng PDCCH/SSB.

### 3.3 FEP và fronthaul không thêm beamforming

`nr_feptx()` trong `openair1/SCHED_NR/nr_ru_procedures.c`:

- Analog BF: copy `beam_id` từ gNB sang RU, rồi vẫn chỉ FFT-shift IQ.
- Không digital beam (`num_dig_beams == 0`) hoặc đang analog BF: copy/FFT-shift, không nhân weight.
- Nhánh còn lại: `AssertFatal("This needs to be fixed by using appropriate beams from config")`.

`nr_beam_precoding()` trong `openair1/PHY/MODULATION/nr_beamforming.c` nhân `beam_weights[p][aa]` lên cả symbol. Không có call site trong cây NR này. Đừng dùng hàm đó như API beamforming đang hoạt động.

`oaioran.c` gán `p_prbMapElm->nBeamIndex` từ `ru->beam_id[]`. Mảng này được cấp phát ở RU và điền −1. Khi analog BF tắt, gNB không cấp `common_vars->beam_id` (`phy_init_nr_gNB()` chỉ malloc khi vendor ext bật). `beam_index_allocation()` trả 0 ngay nếu `beam_id == NULL`. Trên FHI, `beam_id == -1` thì **không** ghi `nBeamIndex` (trừ chế độ Liteon FR2 `RunSlotPrbMapBySymbolEnable`, không phải cấu hình 4T4R này). C-plane vì vậy không mang beamId có nghĩa.

`set_analog_beamforming = PRECONFIGURED_BEAM_IDX` bị `AssertFatal` nếu không phải `NFAPI_MONOLITHIC`. DU Split 7.2 không bật analog beam sweeping bằng tham số đó.

DBT (`dbt_file` / `read_dbt_from_config`) được parse vào FAPI config. FEP không áp các weight đó. Bật `num_dig_beams > 0` trên đường 7.2 hiện tại sẽ dừng process tại `nr_feptx()`.

### 3.4 Uplink

PUSCH/SRS/PUCCH chọn `beam_nb` qua cùng `beam_index_allocation()`. Không analog BF thì mọi thứ ở beam 0. IQ từng anten RX nằm trong `rxdataF[beam][ant]`. Không có bước nhân vector thu trước khi nén U-plane lên DU. SRS phục vụ ước lượng kênh UL tại DU; RU không tự suy góc UE.

---

## 4. Thử phase tại OAI khi RU không có precoding matrix

### 4.1 Việc làm được

Nhân mỗi luồng anten bằng \(e^{j\phi_a}\) trong miền tần số, **trước** `nr_feptx()` / nén BFP:

\[
x'_a[k] = x_a[k] \, e^{j\phi_a}, \qquad e^{j90^\circ} = j \Rightarrow I+jQ \mapsto -Q+jI
\]

Điều kiện để phép đo RF có nghĩa:

1. Bốn eAxC DL (PC_ID `0x0000`–`0x0003` trong conf 4x4) map tới bốn TX chain, RU không gộp và không nhân weight riêng.
2. Cùng một waveform (hoặc cùng waveform đã nhân trọng số) có mặt trên ít nhất hai anten. Nếu chỉ anten 0 khác 0, pha anten 1–3 không xuất hiện trên phổ.
3. Mọi RE mà UE dùng để giải (data và DM-RS của kênh đó) chịu cùng \(\phi_a\).
4. Không nhân thêm một precoder nữa ở RU. Áp \(W\) hai lần làm sai pha và công suất.
5. Đo pha tương đối bằng VSA trên từng cổng, hoặc giữa các cổng đã hiệu chuẩn. Góc tới vật lý còn phụ thuộc khoảng cách phần tử, tần số và sai pha RF cố định. `beamId` không mã hóa góc đó.

Ví dụ bốn phần tử, \(d = \lambda/2\), \(\theta = 30^\circ\):

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

Pha lần lượt \(0^\circ, -90^\circ, -180^\circ, -270^\circ\). Đây là vector minh họa, không phải bảng beam của RU.

### 4.2 Hai cách, khác mức độ sẵn có trong code

**Cách A — dùng precoder PDSCH đã có.** Không cần RU nhận \(W\).

- Tắt `independent_stream_mode` (đường đó cấm PMI khác 0).
- Giữ `identity_precoding_matrix = 0`.
- Một layer, một codeword.
- Chọn một `pm_idx` trỏ vào hàng codebook 4-port đã sinh trong `init_DL_MIMO_codebook()`, hoặc ghi đè `pmi_pdu[].weights` bằng vector pha Q15 ở trên.
- `nr_layer_precoder_simd()` trải layer đó lên bốn anten. DM-RS đi cùng nên UE single-layer vẫn bám kênh, miễn là UE thấy được tổ hợp không gian (anten thật hoặc bộ cộng RF). Trên VSA từng cổng, biên độ PDSCH xuất hiện trên cả bốn đường với pha của \(w\).

Giới hạn: SSB và PDCCH vẫn ở anten 0. Pattern không gian của SSB không đổi, trừ khi replicate SSB rồi mới xoay. Codebook Type I không phải phase shifter analog và không cập nhật theo SRS trừ khi MAC đổi PMI từ CSI.

**Cách B — xoay pha cả symbol, sau khi mọi kênh đã ghi `txdataF`.** Phù hợp thí nghiệm “cổng RF có giữ lệch pha không”.

Điểm chèn đúng: đầu `nr_feptx()`, trước `fft_shift()`, trên `gNB->common_vars.txdataF[bb][aa]`. Một hệ số Q15 mỗi anten, nhân mọi RE của các symbol sắp phát.

Muốn SSB/PDCCH cũng tham gia beam thì phải **replicate** chúng từ anten 0 sang anten 1..3 *trước* bước nhân pha. Nếu không, chỉ PDSCH (và chỉ khi PDSCH đã được trải bằng cách A hoặc bằng bản copy) mang năng lượng trên các cổng kia.

Không sửa IQ sau BFP. Không sửa riêng PDSCH trong `do_txdataF()` nếu DM-RS không đi cùng vòng lặp đó — trên code hiện tại DM-RS đã đi cùng, nên cách A an toàn với PDSCH; cách B an toàn với mọi kênh đã nằm trong `txdataF`.

### 4.3 Việc không làm được bằng cách sửa OAI

- Bật một cờ rồi kỳ vọng RU áp precoding matrix. Source không gửi ma trận đó.
- Dùng `set_analog_beamforming` trên DU FHI 7.2 để RU đổi phase shifter. Đường analog trong OAI gắn monolithic, và beamId chỉ là chỉ số, không phải góc.
- Coi `nr_beam_precoding()` hoặc DBT là đường đang chạy. Caller không có; FEP assert nếu bật digital beam table.
- Suy ra hướng UE từ SRS rồi RU tự xoay. SRS dừng ở ước lượng kênh DU.
- Đo beam pattern chỉ bằng throughput UE. Cần pha tương đối từng TX chain, rồi mới đến mẫu bức xạ.

---

## 5. Việc nên xác nhận trên hệ đang chạy trước khi sửa pha

1. **Bốn eAxC thật sự tách.** Conf TM 4x4 ghi `nb_tx = nb_rx = 4` và PC_ID `0x0000`–`0x0003`. Capture U-plane: bốn PC_ID, IQ khác 0 trên cổng được replicate hoặc được precoder trải. Cổng toàn 0 thì pha không đo được.
2. **RU không beamform thêm.** M-plane / vendor capability: không weight-based DL, không bảng beamId mà RU tự nhân. Nếu RU vẫn áp một beam mặc định lên mọi eAxC, lệch pha DU bị cộng với pha analog của RU.
3. **C-plane không mang weight.** Kỳ vọng section thường (Type 1) mô tả symbol/PRB/eAxC. `nBeamIndex` trên đường OAI mặc định không được set từ `beam_id` (giá trị −1 bị bỏ qua).
4. **Đường PHY đang dùng.** Nếu log hoặc conf có `independent_stream_mode = 1`, PDSCH là identity trên một anten. Thí nghiệm codebook (cách A) phải tắt mode này. `dl_tx_eaxc_mask` chỉ chọn eAxC cho bản copy SSB trong phy-test, không tạo lệch pha.
5. **Đo.** Cùng một symbol: công suất và pha tương đối bốn cổng TX, EVM từng cổng. Đổi \(\phi\) rồi đo lại. Thông UE chỉ là bước sau, khi DM-RS và data cùng pha và UE nằm trong hướng cộng hưởng.

---

## 6. Tóm tắt để trình bày

- Static / dynamic mô tả **trọng số đến từ đâu**. Trên OAI này, trọng số PDSCH đến từ codebook Type I trong DU, hoặc từ identity. RU không nằm trong vòng tính \(W\).
- OAI **đã** thực hiện digital precoding PDSCH trong `do_txdataF()` → `nr_layer_precoder_simd()`. IQ trên eAxC là kết quả. RU không hỗ trợ precoding matrix vẫn phát được các luồng đó.
- OAI **chưa** thực thi digital beamforming theo beamId/DBT (`nr_feptx` assert, `nr_beam_precoding` không được gọi). Analog beamId **có code** nhưng tắt trên Split 7.2 và không điều khiển phase shifter RU.
- SSB/PDCCH mặc định một anten. Phy-test chỉ nhân bản SSB cùng pha.
- Thí nghiệm pha hợp lệ: trải cùng tín hiệu lên các eAxC, nhân \(e^{j\phi_a}\) trước fronthaul, giữ DM-RS cùng pha với data, đo tại cổng RF. Đó là precoding số tại DU, không phải điều khiển beam analog của RU.
