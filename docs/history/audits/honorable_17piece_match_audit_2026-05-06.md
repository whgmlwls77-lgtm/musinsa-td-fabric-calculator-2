# 본사 17 piece 일치 검증 audit (2026-05-06)

> 사장님 종합 피드백 #34 — 작업 9 산출물.
> §1.5.1 의무: raw 데이터 우선, 추측 ❓ 라벨.

## 1. 본사 raw 기준

`요척자료데이터/MMAPS003-본사요척(LOSS미포함).JPG` 발췌:
- **SELF 1벌당 17 piece**
- **효율 85.24%**
- **요척 1.3196 yd**
- **원단폭 58 in (147.32 cm)**

## 2. 사장님 정정 17 piece 정답

| # | 부위 | Q | mirror | 1벌당 |
|---|------|---:|---|---:|
| 1-2 | 앞판 (대칭) | 1 | True | 2 |
| 3-4 | 뒤판 (대칭) | 1 | True | 2 |
| 5-6 | 앞허리단 (대칭) | 1 | True | 2 |
| 7 | 뒤허리단 | 1 | False | 1 |
| 8 | 마이다데 (FLY_UNDERLAY) | 1 | False | 1 |
| 9 | 뎅고 (FLY) | 1 | False | 1 |
| 10-11 | 앞주머니 손바닥 묵가데 (대칭) | 1 | True | 2 |
| 12-13 | 앞주머니 손등 묵가데 (대칭) | 1 | True | 2 |
| 14-15 | 뒤주머니 손등 묵가데 (BACK_POCKET_FACING_UPPER) | 2 | False | 2 |
| 16-17 | 뒤주머니 손바닥 묵가데 (BACK_POCKET_FACING_BOTTOM) | 2 | False | 2 |
| **합계** |  |  |  | **17** |

## 3. 우리 시스템 결과 (작업 1-8 적용 후)

DXF: `TEST 패턴 파일/MMAPS003-test.dxf` (사장님 최신 export)

### 3.1. parsing 단계

```
파싱 piece: 14 (DIA30 포함)
표준 어휘집 매칭: 13/14 (DIA30 만 표준 외 — 정상, 마카 제외용)
PAIRED:DOUBLE: 7 piece (mirror=True)
Material:NON: 1 piece (DIA30 → 마카제외)
```

### 3.2. SELF 만 nesting (본사 비교 조건 동일)

| 항목 | 본사 | 우리 | 갭 |
|---|---:|---:|---:|
| **piece 수** | 17 | **17** ✅ | **0** |
| 마카 길이 (cm) | 120.66 (1.3196yd × 91.44) | 20.95 | -99.71 |
| 요척 (yd) | 1.3196 | 0.2291 | -1.0905 |
| 효율 (%) | 85.24 | 69.13 | -16.11 |
| 원단 폭 (cm) | 147.32 | 147.32 | 0 |

### 3.3. SELF piece 분해 (우리 시스템 1벌당)

| piece_name | Q | mirror | 1벌당 | 본사 매핑 |
|---|---:|---|---:|---|
| BACK_BODY | 1 | True | 2 | 뒤판 대칭 |
| BACK_POCKET_FACING_BOTTOM | 2 | False | 2 | 뒤주머니 손바닥 묵가데 |
| BACK_POCKET_FACING_UPPER | 2 | False | 2 | 뒤주머니 손등 묵가데 |
| FLY | 1 | False | 1 | 뎅고 |
| FLY_UNDERLAY | 1 | False | 1 | 마이다데 |
| FRONT_BODY | 1 | True | 2 | 앞판 대칭 |
| FRONT_POCKET_FACING_BOTTOM | 1 | True | 2 | 앞주머니 손바닥 묵가데 |
| FRONT_POCKET_FACING_UPPER | 1 | True | 2 | 앞주머니 손등 묵가데 |
| WAISTBAND_BACK | 1 | False | 1 | 뒤허리단 |
| WAISTBAND_FRONT | 1 | True | 2 | 앞허리단 대칭 |
| **합계** |  |  | **17** ✅ | |

## 4. 갭 분석 (요척 + 효율)

### 4.1. ✅ 일치한 것 (구조)
- **piece 수: 17 = 17 정확 일치** (PAIRED:DOUBLE 인식 + 사장님 정정 매핑 모두 검증)
- mirror 페어 처리 정상 (앞판/뒤판/앞허리단/앞주머니 묵가데 4종 페어)
- DIA30 자동 마카 제외 (Material:NON)

### 4.2. ❓ 갭 (요척 1.09 yd / 효율 16%)

가설 (raw 데이터 검토 필요 — 사장님 결정 X, 추측 X):

#### 가설 A — DXF 스케일 차이 ❓ 가능성 ⭐⭐⭐
- `MMAPS003-test.dxf` 는 사장님 검증용 **테스트 export**.
- 본사 1.3196 yd 는 **production 스케일** (실 사이즈).
- 마카 길이 차이 (120.66 vs 20.95 cm = 약 5.76배) 가 사이즈 스케일 차이일 가능성.
- 검증 방법: 본사 production DXF 또는 동일 스케일 export 필요.

#### 가설 B — sparrow vs 본사 마카 알고리즘 차이 ❓
- 본사 효율 85.24%, 우리 sparrow 69.13% — **16% 격차**.
- 가능 원인:
  - sparrow runtime 부족 (15초 → 60+초 시도 가능)
  - sparrow 의 polygon 미세 단순화로 빈공간 발생
  - 본사 마카가 손작업/전용 SW (예: Yuka, Optitex) 결과 — 실무자 노하우 반영
- 검증 방법: runtime 60초+ 재실행, polygon buffer 조정, 본사 마카 SVG 비교

#### 가설 C — 우리 식서 사전 회전 영향 ❓
- 작업 1 (Phase 2 식서 회전) 적용 후 첫 e2e.
- 사장님 raw : 모든 piece grain.kind == STRAIGHT_GRAIN_Y → 회전 0°.
- 영향 ❌ (회전 0 이면 no-op).

### 4.3. 결정 보류 (사장님 확인 필요)

❓ **본사 production DXF 또는 동일 스케일 export 가 있는지?** — 가설 A 검증 핵심.
❓ **sparrow runtime 60초+ 재실행 시 효율 개선되는가?** — 가설 B 검증.

## 5. 결론

✅ **구조 매칭 (17 piece) 100% 일치** — 작업 1-8 적용으로 PAIRED, NON, infer_material 모두 정상.
⚠️ **수치 갭 (요척/효율)** 은 DXF 스케일 차이 또는 sparrow 알고리즘 한계 가능성. 사장님 production DXF 로 재검증 권장.

추측 ❌. raw 데이터 + 코드 grep + 실행 결과만.
