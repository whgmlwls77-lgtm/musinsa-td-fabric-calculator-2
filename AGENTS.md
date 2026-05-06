# 원단 요척 산출 시스템 — Codex / AI Agent 컨텍스트

> 매 세션 첫 읽기 (Codex / Cursor / 기타 AI 에이전트).
> Claude Code 는 `CLAUDE.md` 동일 내용 — 둘 모두 동기화 유지.
> 변동 사항: `PROJECT_STATUS.md` 참조.
> 상세 사양: `specs/PATTERN_PREP_GUIDE.md` (v2.0 정식).

## 1. 본질 (5줄)

의류 패턴 DXF → 자동 마카 + 원단 요척 산출.
사용자: 무신사 TD팀 **소싱팀** (패턴 모름).
협력사: 패턴사 (StyleCAD / Yuka 등 사용).
시스템: **raw 데이터 처리** (추측 X).
현재: v3.3 베타 (jagua-rs sparrow polygon NFP).

## 2. 사장님 절대 원칙 (3개)

1. **raw 데이터 우선, 추측 금지** — DXF 명시된 정보만 사용. 누락 시 사용자에게 명시 입력 요구.
2. **결정은 사장님, 클로드 = 제안 + 처리** — 추천 시 근거 라벨 (✅/❌) 의무. 정석 인정한 영역 추측으로 뒤집기 금지.
3. **표준만 인식 (표준 외 = 위반 알림)** — 협력사 가이드 = 시스템 인식 어휘. 알파벳 하나 틀려도 위반 알림 (정상은 침묵).

## 3. 사장님 본질 6가지 (영구 박제 — 사용자 피드백 #34/#36)

1. **식서 = 요척 핵심** — "식서 못 읽으면 요척 의미 없음"
2. **원단 = 사용자 설정 그대로** — 패턴명과 별개 ("패턴명이 POCKETING 이라고 원단이 POCKETING 인 거 아님")
3. **표준 정립 → 가이드 박제 → 시스템은 표준만 인식** — 표준 외 위반 알림
4. **협력사 메시지 = 평이한 한국어** — "협력사는 프로그래머 아님"
5. **마카 = 본사처럼 한눈에** — 가로 1줄, 스크롤 없이 (본사 요척서 컨벤션)
6. **진단 = 위반만 알림** — 정상은 침묵

## 4. 표준 정의 (협력사 가이드 = 시스템 인식)

| 항목 | 표준 |
|------|------|
| **원단 5종** | `SELF` / `LINING` / `POCKETING` / `CONTRAST` / `NON` |
| 마카 제외 | `Material: NON` (StyleCAD 마커 제외 우회) |
| 좌우 페어 | `PAIRED: DOUBLE` → mirror=True (q=1 + 페어) |
| 단위 보정 | **50cm × 50cm 박스** (Material:NON, Piece Name:SCALE_BOX) |
| 부위명 | `data/panel_mapping.json` 표준 어휘집 + 약자 (FB/BB/WBF 등) |
| 식서 LAYER | `"7"` 또는 `"GRAIN"` (전용 LAYER, LINE 30mm 이상) |

상세: `specs/PATTERN_PREP_GUIDE.md` v2.0 §1~§9.

## 5. 시스템 흐름 (5단계)

```
DXF 업로드
    ↓
[1] parse_dxf_v3 (extract_pieces + 메타 파싱)
    ↓
[2] 자동 단위 보정 (50cm × 50cm 박스 → ×ratio)  ← 사용자 피드백 #36
    ↓
[3] 진단 리포트 (5 카테고리: 결방향/원단/패널/수량/스케일)
    ↓
[4] 재질별 sparrow nesting (auto_nesting_v2)
    ↓
[5] 결과 화면 (마카 SVG + 본사 비교 expander + PDF/Excel)
```

## 6. 프로젝트 구조 (카테고리 7개)

| 카테고리 | 위치 | 내용 |
|---------|------|------|
| **본질 (루트)** | `*.py` + `CLAUDE.md` + `AGENTS.md` + `PROJECT_STATUS.md` + `README.md` | 코드 + 컨텍스트 |
| **사양 (specs/)** | `PATTERN_PREP_GUIDE.md` + `USER_GUIDE.md` + `DXF_조회_리스트.md` | 협력사/사용자 사양서 |
| **데이터 (data/)** | `panel_mapping.json` + `material_mapping.json` | 표준 어휘집 |
| **검증 (tests/)** | `test_*.py` (18 파일) | 단위 테스트 |
| **히스토리 (docs/history/)** | `audits/` (보존 3개) + `feedback/` (#1~#36) | 결정 근거 박제 |
| **임시 (workspace/)** | `logs/` + `scratch/` | gitignore — 커밋 X |
| **사장님 영역** ⛔ | `요척 자료 데이터/` + `요척 패턴 데이터/` + `TEST 패턴 파일/` | **절대 X — gitignore** |

## 7. 핵심 파일 (꼭 알아야 할 것만)

| 파일 | 역할 |
|------|------|
| `app.py` | 메인 Streamlit 앱 (v3.3, ~3,300줄) |
| `extract_pieces.py` | DXF → piece 추출 + 메타 파싱 |
| `auto_nesting_v2.py` | jagua-rs sparrow polygon NFP nesting (Phase 2) |
| `dxf_diagnosis.py` | 5 카테고리 진단 리포트 + 50cm 박스 자동 보정 |
| `grain_extractor.py` | 식서 LAYER 인식 + 회전 정렬 |
| `piece_name_normalize.py` | 부위명 표준 어휘집 정규화 (panel_mapping.json) |
| `visualize_pieces.py` | 마카 SVG 시각화 (본사 컨벤션) |
| `data/panel_mapping.json` | 부위명 표준 어휘집 + 약자 |
| `bin/sparrow-darwin-arm64` | jagua-rs sparrow 바이너리 (macOS arm64) |
| `specs/PATTERN_PREP_GUIDE.md` | 협력사 사양서 v2.0 정식 |
| `tests/test_*.py` | 단위 테스트 (210/210 PASS) |

## 8. 헛발질 방지 (자기 약속)

1. **사장님 raw 메시지 우선** — PDF/캡쳐/audit md 직접 읽기. 추측 X.
2. **추측 단어 금지** — "가능성 / 추정 / 옵션" 으로 결정 떠넘기기 X. 추천 시 ✅/❌ 라벨 의무.
3. **사장님 결정 떠넘김 금지** — 클로드 처리 영역 (제안 + 코드/문서 작업) 명확히. 결정만 사장님.
4. **정석 알면서 추측으로 뒤집기 금지** — 사용자 피드백 #30 (atomic commit / 책임 분리 영구 박제).
5. **1차/2차 임의 분리 금지** — 사장님 본질대로 한 번에 처리.

### 8.1. 답변 전 자가 검증 체크리스트 (사용자 피드백 #38 — 영구 박제)

매 답변 출력 전 자가 점검 (필수):

- [ ] **사장님 명령 정의 그대로** 받았나? (가설 명칭 / 본문 임의 변경 X)
- [ ] **이전 답변 박은 본질** 빠뜨림 0건? (한 가지 집중 시 다른 거 누락 차단)
- [ ] **추측 단어** ("가능성", "추정", "아마", "옵션") 0건?
- [ ] **라벨** (✅/❌/⚠️/❓) 박혀있나?
- [ ] **Tool 우선** — 사장님께 묻기 전 Read/Bash/Grep 으로 직접 검증?
- [ ] **명령 본문 보존** — "이전 명령 그대로" 식 줄임 금지, full text 박음?

체크 미달 시 → 답변 거부 또는 보강 후 출력.

**진짜 본질**: 사장님이 검증자 역할 X. 클로드가 자가 검증 후 답변.

---

## 9. 빠른 실행

```bash
source venv/bin/activate
streamlit run app.py                              # 앱 실행 (http://localhost:8501)
python -m unittest discover -s tests -p "test_*.py"  # 회귀 테스트 (210/210 PASS)
python regression_test.py                         # 회귀 시나리오
```

## 10. UI 라벨 규약 (혼동 주의)

| 라벨 | 의미 |
|------|------|
| 기준사이즈 | 마카의 base 사이즈 (예: L) |
| 패턴 갯수 | 1벌당 unique 패턴 수 (예: 6) |
| 마카 갯수 | 마카에 실제 깔린 총 piece 수 (예: 12) |

- "조각 수" 사용 X (모호) → 위 3개 라벨로만 표기
- "미러" 사용 X → "1WAY/2WAY" (의류업계 표준)
- 본사 비교는 **1벌당 요척(yd)** 만 fair 메트릭 (효율 % 는 마카 구성 다르면 비교 무의미)

## 11. 도메인 용어 (간략)

| 한글 | 영문 | 설명 |
|------|------|------|
| 요척 | fabric consumption | 의류 1벌당 원단량 |
| 마카 | marker | 원단 위 패턴 배치도 |
| 식서 | grain | 원단 직조 방향 |
| 시접 | seam allowance | 봉제용 여유분 (1cm 표준) |
| LOSS | loss | 끝단 손실 + 결함 처리분 |
| 사이바 | side body | 옆판 (한일혼용 방언) |
| 마이다데 | fly underlay | FLY 안쪽 보강 |
| 뎅고제감 | fly | FLY 본체 (지퍼 덮개) |

## 12. 주요 의사결정 (commit 박제)

| 시점 | 결정 | commit |
|------|------|--------|
| 2026-04-28 | jagua-rs sparrow 채택 (Phase 2) | (Phase 2-A 본체) |
| 2026-04-30 | 5가지 자동 추정 fallback 정정 (절대원칙) | (Phase 2-B-5) |
| 2026-05-04 | 옵션 A 미러 처리 + §1.5.1 책임 분리 박제 | `850b864`, `870d241` |
| 2026-05-05 | Material:NON 단일 표기 (StyleCAD 우회) | (피드백 #32) |
| 2026-05-06 | 사장님 본질 6 + 표준 5종 (심지 폐기) | `42209a6`, `4f16b5d` |
| 2026-05-07 | 50cm × 50cm 박스 자동 보정 (옵션 A) | `2bbefc3` |
| 2026-05-07 | PATTERN_PREP_GUIDE v2.0 정식 승격 | `0e0b490` |
| 2026-05-07 | 답변 전 자가 검증 체크리스트 §8.1 박제 (피드백 #38) | (다음 commit) |

---

*마지막 갱신: 2026-05-07 (자가 검증 체크리스트 §8.1 추가 — 사용자 피드백 #38)*
