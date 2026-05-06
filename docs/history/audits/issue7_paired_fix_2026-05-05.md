# Issue 7 Fix Report — PAIRED:DOUBLE 메타 처리 (2026-05-05)

## 1. 요약

`TEST 패턴 파일/MMAPS003-test.dxf` 의 좌우 페어 piece 8개가 마카에 한쪽만 깔리던 버그(64 placements / 4벌) 를 수정해 정상 96 placements 로 복원.

**근본 원인**: 사장님이 StyleCAD 표기 관습으로 박은 `PAIRED: DOUBLE` 메타를 parser 가 인식 못 함 → mirror=None → `_split_mirrored_pieces` skip → 좌우 1쌍 중 1장만 nesting.

## 2. raw 데이터 검증 (사장님 §1.5.1 의무)

`MMAPS003-test.dxf` 파싱 raw (수정 전 동일):

| piece_name | qty | PAIRED | material |
|---|---:|---|---|
| MMAPS003 DIA30 | 1 |  | SELF |
| FRONT_POCKET_FACING_BOTTOM | 1 | DOUBLE | SELF |
| FRONT_POCKET_FACING_UPPER | 1 | DOUBLE | SELF |
| FLY | 1 |  | SELF |
| FLY_UNDERLAY | 1 |  | SELF |
| BACK_POCKET_FACING_UPPER | 2 |  | SELF |
| BACK_POCKET_FACING_BOTTOM | 2 |  | SELF |
| WAISTBAND_FRONT | 1 | DOUBLE | SELF |
| WAISTBAND_BACK | 1 | DOUBLE | SELF |
| FRONT_POCKET_BAG | 1 | DOUBLE | Lining |
| BACK_POCKET_BAG | 1 | DOUBLE | Lining |
| BACK_BODY | 1 | DOUBLE | SELF |
| FRONT_BODY | 1 | DOUBLE | SELF |
| FLY_FACING | 1 |  | Lining |

- 총 14 piece, PAIRED:DOUBLE 8개 (모두 Quantity:1)
- 1벌당 piece: unpaired 4×1 + 2×2 + paired 8×(1+1) = 4+4+16 = **24** ✓
- 4벌: **96 placements** ← 사장님 raw 카운트와 일치

## 3. 수정 사항

### 3.1 Parser — PAIRED 키 인식 (절대 원칙: 추측 X, 토큰 매칭만)

| 파일 | 함수 | 변경 |
|---|---|---|
| `extract_pieces.py` | `parse_paired_value` (신규) + `parse_piece_metadata` | `paired` 키 처리 + PAIRED > Mirror 우선순위 |
| `app.py` | `parse_paired_value_v3` (신규) + `parse_block_metadata_v3` | 동일 |

토큰 매핑:
- True : `DOUBLE` / `PAIR` / `YES` / `Y` / `TRUE` / `1`
- False: `SINGLE` / `NO` / `N` / `FALSE` / `0` / `""`
- 그 외 → `None` (사장님 §1.5.1 — 자동 추측 금지)

PAIRED 우선순위: TEXT 엔티티 순회 시 `paired_seen` flag 로 PAIRED 가 이미 mirror 를 정한 후엔 Mirror 키가 덮어쓰지 못함.

### 3.2 정책 갱신 — `auto_nesting_v2._split_mirrored_pieces`

**사장님 결정 갱신 (2026-05-04 → 2026-05-05)**:
- 어제: `mirror=True + Q<2` → ⚠️ 경고 + 미러 skip
- 오늘: `mirror=True + Q==1` → "1 pair" 의미 → orig:1 + mirror:1 (총 2 piece)

이는 StyleCAD 의 `PAIRED:DOUBLE + Quantity:1` 표기 관습 (1을 적었지만 좌우 1쌍 의미) 을 수용하기 위함.

| Q | mirror=True 결과 |
|---:|---|
| 1 | **orig:1 + mirror:1** (NEW — 1 pair) |
| 2 | orig:1 + mirror:1 (기존) |
| ≥4 짝수 | orig:Q/2 + mirror:Q/2 (기존) |
| ≥3 홀수 | ⚠️ 경고 + skip (기존) |

기존 `test_mirror_handling.py:test_case_4b_mirror_quantity_1` 도 신정책에 맞춰 업데이트.

### 3.3 MATERIAL 대소문자 정규화 — 검증 결과

`infer_material_v3` (app.py) 는 이미 `(material_raw or "").strip().upper()` 로 정규화 후 비교 → "Lining" / "lining" / "LINING" 모두 LINING 으로 매칭. **별도 수정 불필요**.

단, 우선순위가 (1) annotations → (2) piece_name 키워드 → (3) material_raw 코드 이므로, piece_name 에 "POCKET" 등 키워드가 있으면 material 코드보다 piece_name 이 우선. 예: FRONT_POCKET_BAG + Lining → "주머니감" (의도된 동작).

## 4. 검증 결과

### 4.1 수정 전/후 placements 비교 (4벌 기준)

```
수정 전 (PAIRED 무시): 12×1 + 2×2 = 16/벌 × 4 = 64 placements
수정 후 (PAIRED 인식): 24/벌 × 4 = 96 placements  ✅ 사장님 raw 와 일치
```

### 4.2 단위 테스트 (44/44 통과)

신규 `test_paired_metadata.py` (17 tests):
- ✅ `parse_paired_value` 토큰 정규화 (True/False/None 매핑)
- ✅ `parse_piece_metadata` PAIRED 인식 (DOUBLE/SINGLE/부재/우선순위)
- ✅ `_split_mirrored_pieces` Q=1 신정책 + Q=2/Q=3 기존 정책
- ✅ MATERIAL 대소문자 무시 (Lining/SELF 케이스)
- ✅ MMAPS003-test.dxf 통합: 14 piece 중 8개 mirror=True 확인

기존 `test_mirror_handling.py` (27 tests, Q=1 케이스 1개 정책 갱신):
- ✅ 27/27 통과

### 4.3 회귀 sweep (28+1 사내 DXF)

| DXF | piece | mirror=True | mirror=None | PAIRED text | 영향 |
|---|---:|---:|---:|---:|---|
| 27 DXF | (다양) | **0** | 100% | 0 | **회귀 X** ✅ |
| MMAPS003-test.dxf | 14 | 8 | 6 | 8 | **목표 fix** ✅ |
| MMJTP201.dxf | 35 | **20** | 15 | 20 | **추가 fix** ⚠️ |
| MMAPS002.dxf | (읽기 실패 — pre-existing 손상) | | | | 무관 |

⚠️ **추가 발견**: `MMJTP201.dxf` 도 같은 버그의 피해자였음. 사장님이 자켓에도 PAIRED:DOUBLE 박았는데 무시되고 있었음. 본 fix 로 자동 정상화됨. 사장님 수동 확인 권장.

## 5. 변경된 파일

```
M  extract_pieces.py        +29 (parse_paired_value 신규 + parse_piece_metadata 확장)
M  app.py                   +35 (parse_paired_value_v3 신규 + parse_block_metadata_v3 확장)
M  auto_nesting_v2.py       +14/-7 (_split_mirrored_pieces Q=1 분기 추가)
M  test_mirror_handling.py  +5/-3 (test_case_4b 신정책 반영)
A  test_paired_metadata.py  +280 (PAIRED + 정책 갱신 + 통합 테스트)
A  output/issue7_paired_fix_2026-05-05.md  (본 보고서)
```

## 6. 사장님 확인 요청 사항

1. **정책 변경 박제 OK?** — `_split_mirrored_pieces` 의 Q=1 처리: 어제 (skip) → 오늘 (1 pair). PROJECT_STATUS.md 도 갱신 필요?
2. **MMJTP201.dxf 도 본 fix 영향**받음 (20 paired piece). 의도된 거지만, 기존 마카 결과가 변하므로 보고만 드림.
3. PAIRED 토큰 매핑 (DOUBLE/PAIR/YES → True, SINGLE/NO → False) 으로 충분한가? 다른 변형 (TWIN/COUPLE 등) 도 추가할지?
