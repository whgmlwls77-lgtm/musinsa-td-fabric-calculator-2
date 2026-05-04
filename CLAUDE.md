# 원단 요척 산출 시스템 — 프로젝트 컨텍스트

> 이 파일은 Claude Code가 매 세션 읽는 프로젝트 컨텍스트입니다.
> 변경 시 간결하게 유지하세요. 세부 가이드는 별도 문서에 두고 여기서는 위치만 참조.
>
> **🔥 최신 진행 상황은 `PROJECT_STATUS.md`를 먼저 읽으세요** (단일 진실 공급원).
> 이 CLAUDE.md는 안정적인 컨텍스트만 담고, 변동 사항은 PROJECT_STATUS.md에서 관리.

## 1. 한 줄 요약

의류 패턴 **DXF 파일에서 자동 마카 배치 + 원단 요척**을 산출하는 Streamlit 웹앱.
무신사 TD팀 사내 도구. 사용자: **소싱팀**(패턴사 X). 현재 **v3.3 베타** (jagua-rs sparrow 도입).

## 1.5. 🚨 절대 원칙 — 매 세션 최우선 (2026-04-30 사장님 명시)

> **"원리·개념·분석·근거로만 일해야 한다. 추측이나 임의 처리는 금지."**

- **DXF raw 데이터 → 검토 → 명시된 대로 처리**. 누락 시 알고리즘 추정 X.
- **금지**: bbox 비율로 결방향 추정 / 이름 substring으로 재질 추측 / 좌우 자동 미러
- **의무**: 분류 결과 변경 시 raw 데이터(piece_name, material_raw, annotations, quantity) 출력으로 입증
- **데이터 누락 시**: 사용자/패턴사에게 "패턴 파일에 X 누락 — 표기 필요" 명확히 안내. fallback 금지.

### 요척 산출 4대 핵심 요소 (하나라도 빠지면 결과 무의미)
1. **재질별 분리 마카** — SELF/FUSE/LINING/CONTRAST/POCKET 각 별도 마카·요척
2. **결방향 정확히** — 식서/푸서/바이어스, 회전 정렬 후 배치
3. **벌수 + 1WAY/2WAY** — 마카 갯수 = `Σ(piece.quantity) × n_lay`. 1WAY=식서통일(0°), 2WAY=180°교차 허용
4. **본사 검증 데이터 사용자 노출 X** — 결과·PDF·Excel 어디에도 본사 비교 표시 금지 (소싱팀은 본사 데이터 미보유)

상세 근거 / 검증 데이터 / 진행 상황 → **`PROJECT_STATUS.md`** (단일 진실 공급원)

### 1.5.1. 책임 분리 — 사장님 명시 (2026-05-04)

- **모든 결정은 사장님이 한다. 클로드는 결정 X.**
- 클로드 역할: **제안 + 처리(수행)**.
- 클로드는 옵션을 **정직하게 나열**하고 각각의 **근거·데이터를 보여줄 의무**가 있음.
- "추천"을 할 때는 반드시 **근거 라벨 첨부** (✅ 데이터 기반 / ❌ 추측).
  **추측 라벨이 붙은 추천은 결정 근거로 채택 불가.**
- **정석/표준이 있는 영역에서 추측으로 정석을 뒤집는 추천 금지.**

근거: 사용자 피드백 #30 (2026-05-04) — `PROJECT_STATUS.md` 상단 영구 박제. commit 850b864 분리 결정 시 정석(atomic commit) 인정 직후 추측 근거로 정석 뒤집은 사례.

## 2. 핵심 파일 (꼭 알아야 할 것만)

| 파일 | 역할 | 주의 |
|------|------|------|
| `app.py` | 메인 Streamlit 앱 (V3, ~3,300줄) | **이게 본체**. v1/v2 백업은 참고만 |
| `extract_pieces.py` | DXF → 피스(블록) 추출 + Shapely 폴리곤화 | `find_outline()`, `parse_piece_metadata()` 재사용 |
| `grain_extractor.py` | 식서/푸서/바이어스 LAYER 인식 | 점수제 — 28 DXF 모두 LAYER "7"/"5" 일관 |
| `mirror_pieces.py` | 좌우 미러링 헬퍼 | ❌ 자동 미러 폐기 (절대 원칙). Quantity 메타 그대로 사용 |
| `auto_nesting.py` | **Phase 1**: rectpack bbox nesting (5초, 빠름) | |
| `auto_nesting_v2.py` | **Phase 2 ⭐**: jagua-rs sparrow polygon NFP (30초, 정확) | `bin/sparrow-darwin-arm64` 바이너리 호출 |
| `dxf_diagnosis.py` | DXF 4대 카테고리 진단 (결방향/원단/패널/수량) | 알고리즘 실패 vs 협력사 누락 구분용 (2026-05-02) |
| `fabric_calculator.py` | 요척 계산 엔진 (CLI 버전) | |
| `visualize_pieces.py` | matplotlib 패턴 프리뷰 | |
| `explore_dxf.py` | DXF 구조 탐색 헬퍼 (`open_dxf()` 재사용) | DXF 헤더 `$INSUNITS` **신뢰 금지** — 좌표값으로 단위 추정 |
| `validate_against_reference.py` | 본사 검증 데이터 비교 (스켈레톤) | 채워야 함 |
| `regression_test.py` | 회귀 테스트 | 변경 후 반드시 실행 |
| `bin/sparrow-darwin-arm64` | jagua-rs sparrow 바이너리 (macOS arm64) | Linux 빌드 미생성 — Streamlit Cloud 배포 시 필요 |
| `요척자료데이터/` | **본사 실제 요척 자료 (검증 데이터)** | 아래 §4 참조 |
| `output/` | 생성된 리포트 (CSV/JSON/PNG/MD) | 커밋 안 함 |
| `app_v1_backup.py`, `app_v2_backup.py` | 과거 버전 백업 | 손대지 말 것 |

## 3. 빠른 실행

```bash
source venv/bin/activate            # 가상환경
streamlit run app.py                # 앱 실행 → http://localhost:8501
python regression_test.py           # 회귀 테스트
python extract_pieces.py            # CLI로 피스 추출만
```

## 4. 검증 데이터 — 가장 중요 ⭐

`요척자료데이터/` 폴더에 **본사 실제 요척서 48건**이 있음. 앱 계산값을 이 자료와 비교해 정확도 검증.

### 4.1. 인덱스 파일

| 파일 | 용도 |
|------|------|
| `요척자료데이터/요척_검증데이터.csv` | 모든 자료의 **품번/원단폭/요척/효율** 등을 표로 정리 (UTF-8 BOM, Excel 호환) |
| `요척자료데이터/요척_검증데이터.json` | 동일 데이터의 JSON 버전 (프로그램에서 import용) |

### 4.2. 자료 종류 (3가지 포맷)

1. **본사 요척서 (JPG, 37건)** — 한국 의류 CAD에서 출력한 표준 요척 보고서
   - 좌측 상단에 `MWDPS-901 (SELF) (\SLACKS)` 같이 품번/재질/카테고리 명시
   - 핵심 필드: `원단폭(in)`, `길이(yd+in)`, `조각수(N/N)`, `효율(%)`, `LOSS(%)`, **`요척(yd)`**, `사이즈/비율`
   - 하단에 마카 도면 시각화

2. **요척 PDF (6건)** — 더 간결한 표 + 마카 도면
   - 헤더: `마카이름 / 날짜 / 패턴수`, `소재 / 원단폭 / 벌수`, `총장 / 요척 / 효율`

3. **요척마카 PNG (1건)** — 유카(Yuka) 마카 프로그램 화면 캡처
   - 중국어 UI, 효율 % 색상 게이지 표시

4. **AP요척 (2건)**, **위클리플랜 XLSX (코스팅 시트)** — 형식 다름, 별도 처리

### 4.3. 검증 시 주의사항

- **단위는 야드(yd)**가 표준. 미터 변환: `1 yd = 0.9144 m`. 인치: `1 in = 2.54 cm`.
- **LOSS 미포함 vs 포함** 구분 필수 (파일명에 `(LOSS미포함)` / `(NET)` 표기). 앱 계산값과 비교할 때 같은 기준이어야 함.
- **사이즈/비율 표기**: `4:26-4` 같은 형식 — 사이즈 그룹 구성 의미. 실무자 확인 필요한 부분.
- **재질 코드**: `SELF`(주원단), `FUSE`(심지), `LINING`(안감), `CONTRAST`(배색), `POCKET`(주머니감)
- **OCR 자동 추출 9건은 수동 입력 필요** — `요척_검증데이터.csv`의 `비고` 컬럼에 표시됨

## 5. 품번 명명 규칙 (관찰값)

```
M [성별] [시즌/연도] [카테고리] [순번]
│   │      │        │           │
│   │      │        │           └─ 3~5자리 숫자/문자
│   │      │        └─ P=Pants, J=Jacket, S=Shirt/Skirt, K=Skirt, L=?, R=?, T=Tee
│   │      └─ A,B,C,D,E,F,J,P,R,U (시즌 코드 추정)
│   └─ M(남성) / W(여성) / K(키즈?) / F(?) / I(?)
└─ 무신사 브랜드 prefix (추정)
```

예시:
- `MWDPS901` → M-W(여성)-D-P(팬츠)-S-901 → 여성 팬츠/슬랙스
- `MMAPS006` → M-M(남성)-A-P(팬츠)-S-006 → 남성 팬츠
- `MMFLJ1A03` → M-M(남성)-F-L-J(자켓)-1A03

> ⚠️ 위 규칙은 파일 관찰로 추정한 것. **실무자 확인 필요**. 정확한 코드북이 있으면 별도 추가.

## 6. 도메인 용어

| 한글 | 영문 | 설명 |
|------|------|------|
| 요척 | fabric consumption | 의류 1벌 만드는데 필요한 원단량 |
| 마카 | marker | 원단 위 패턴 배치도 |
| 그레이딩 | grading | 사이즈별 패턴 확대/축소 |
| 시접 | seam allowance | 봉제용 여유분 (1cm 표준) |
| 결방향 | grain direction | 원단 직조 방향 |
| 1WAY | one-way | 단방향 마카 (결방향 한쪽만) |
| 2WAY | two-way | 양방향 마카 |
| LOSS | loss | 끝단 손실분 + 결함 처리분 |
| 본사 요척 | HQ fabric calc | 본사가 산출한 공식 요척 (vs 협력공장) |
| 사이바 | side body | 옆판 (한일혼용 방언) |
| 플래킷 | placket | 셔츠 앞단 |
| 넥밴드 | collar band | 칼라 밑단 |
| 커프스 | cuff | 소매단 |
| 요크 | yoke | 어깨 분할 패널 |

## 6.5. UI 라벨 규약 (혼동 주의 — 사장님 명시)

| 라벨 | 의미 | 예시 |
|------|------|------|
| **기준사이즈** | 마카의 base 사이즈 | L |
| **패턴 갯수** | 1벌당 unique 패턴 수 | 6 |
| **마카 갯수** | 마카에 실제 깔린 총 피스 수 | 12 |

- "조각 수"는 **패턴 파일 조각 수** vs **마카 조각 수** 두 의미가 있어 모호 → 위 3개 라벨로만 표기.
- "미러" 단어 사용 X → "1WAY/2WAY" (의류업계 표준).
- 본사 비교는 **1벌당 요척(yd)**만 fair 메트릭. 효율 %는 마카 구성 다르면 비교 무의미.

## 7. 디자인 토큰 (앱 UI)

```
배경      #ffffff
서피스    #f8fafc
텍스트    #0f172a
서브텍스트 #64748b
보더      #e2e8f0
강조(빨강) #dc2626   ← Primary 버튼 + PDF 타이틀에만 사용
```

## 8. 개발 시 지켜야 할 것

- **함수 단위 분리** + `if __name__ == "__main__":` 관용구 (모듈 import 시 main이 안 돌게)
- **`pathlib.Path`** 사용 — 문자열 경로 X
- **`Counter`, list comprehension** 등 파이썬 관용구 적극 활용
- **타입 힌트** 권장 (`def f(x: Path) -> Counter:`)
- **`partition(":")`** 사용 — `split(":")`은 `08:09` 같은 값에서 깨짐
- **CP949 한글 디코딩** — Yuka(SuperALPHA_Plus) DXF는 한글이 깨져서 옴. `app.py`에 복원 로직 있음
- **에러 처리**: `try/except`로 특정 예외만 잡기. `except Exception:` 남용 금지
- **Shapely**: `Polygon(coords).buffer(0)` 트릭으로 자기교차 폴리곤 수리

## 9. 앞으로 할 일 (LEARNING_NOTES 발췌)

1. **재단 효율 분석** — 피스 합 ÷ bbox × 100 = 효율 %
2. **그레이딩 시각화** — 사이즈별 외곽선 nested 표시
3. **피스 자동 분류** — 외곽선 → KMeans → "FRONT/BACK/SLEEVE" 자동 라벨링
4. **본사 검증 데이터 비교 자동화** — `validate_against_reference.py`(스켈레톤만 있음, 채워야 함)

## 10. 관련 문서

- `README.md` — 사용자용 개요
- `USER_GUIDE.md` — 앱 사용법
- `PATTERN_PREP_GUIDE.md` — 패턴사용 DXF 작성 규칙 (배포용)
- `LEARNING_NOTES.md` — 코드 학습 노트 + 발전 아이디어
- `패턴_준비_가이드.pptx` — 협력업체 배포용 PPT

---
*마지막 갱신: 2026-05-04 (절대 원칙 + 4대 핵심 요소 + Phase 2 모듈 반영)*
