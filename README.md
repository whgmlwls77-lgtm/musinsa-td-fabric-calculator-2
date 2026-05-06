# 원단 요척 산출 시스템

> **사장님 본질**: 의류 패턴 DXF → 자동 마카 + 원단 요척. 본사 패턴사 그 이상 정확도.

의류 패턴 DXF 파일에서 **원단 소요량(요척)을 자동 계산**하는 웹 앱.
무신사 TD팀 사내 도구. 사용자: **소싱팀**.

**현재 버전**: v3.3 베타 (jagua-rs sparrow polygon NFP nesting + 50cm × 50cm 박스 자동 단위 보정)

---

## 주요 기능

- **DXF 파싱** — Optitex / Yuka / SuperALPHA_Plus 등 주요 패턴 CAD 포맷 지원
- **DXF 진단 리포트** — 5 카테고리 (결방향 / 원단 / 패널 / 수량 / 스케일) 자동 진단
- **50cm × 50cm 비율 박스 자동 단위 보정** — DXF 좌표 cm/mm/inch 무관 (사장님 본질, 2026-05-07)
- **재질 자동 분류** — 표준 5종 (`SELF` / `LINING` / `POCKETING` / `CONTRAST` / `NON`)
- **재질별 분리 마카** — 각 재질당 별도 sparrow nesting + 별도 요척
- **결방향 정렬** — 식서/푸서/바이어스 LAYER 인식 + 자동 회전
- **좌우 페어 처리** — `PAIRED: DOUBLE` 메타 (StyleCAD) → mirror 자동 분리
- **본사 비교** — 효율 / 1벌당 요척 / piece 수 갭 (expander)
- **PDF / Excel 리포트** — 한글 폰트, 재질별 상세 + 합계

---

## 로컬 실행

```bash
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

기본 포트: http://localhost:8501

회귀 테스트:
```bash
python -m unittest discover -s tests -p "test_*.py"
# 210/210 PASS (회귀 0)
```

---

## 프로젝트 구조 (카테고리 7)

| 카테고리 | 위치 | 내용 |
|---------|------|------|
| 본질 (루트) | `*.py` + `CLAUDE.md` + `AGENTS.md` + `PROJECT_STATUS.md` | 코드 + 컨텍스트 |
| 사양 | `specs/` | `PATTERN_PREP_GUIDE.md` (v2.0) + `USER_GUIDE.md` |
| 데이터 | `data/` | `panel_mapping.json` + `material_mapping.json` |
| 검증 | `tests/` | 18 단위 테스트 |
| 히스토리 | `docs/history/` | `audits/` + `feedback/` |
| 임시 | `workspace/` | gitignore — logs/scratch |
| 사장님 영역 ⛔ | (gitignore) | `요척 자료 데이터/` + `요척 패턴 데이터/` + `TEST 패턴 파일/` |

---

## 기술 스택

- **UI**: Streamlit
- **DXF 처리**: ezdxf
- **기하 연산**: shapely
- **마카 nesting**: jagua-rs sparrow (Rust 바이너리, polygon NFP)
- **시각화**: SVG 동적 생성 (본사 요척서 컨벤션 — 가로 1줄, 식서 화살표)
- **PDF**: reportlab (한글 폰트 — Noto Sans KR)
- **Excel**: openpyxl

---

## 협력사 가이드

협력사가 DXF 납품 전 다음을 확인 (`specs/PATTERN_PREP_GUIDE.md` v2.0):

```
[ ] 모든 piece 가 블록(Block) 으로 묶여있다
[ ] 모든 piece 에 Piece Name TEXT (영문 부위명, panel_mapping 표준)
[ ] 모든 piece 에 Material TEXT — 5종: SELF / LINING / POCKETING / CONTRAST / NON
[ ] 모든 piece 에 Quantity TEXT (정수)
[ ] 식서 LINE — 전용 LAYER ("7" 또는 "GRAIN") + 30mm 이상
[ ] 외곽선은 닫힌 POLYLINE — 시접 포함된 재단선
[ ] **50cm × 50cm 비율 검증 박스** (Piece Name: SCALE_BOX, Material: NON) ⭐ v2.0 필수
```

---

## 검증 사례 (사장님 본질 솔루션)

**MMAPS003-test.dxf** (2026-05-07 사장님 raw):
- 박스 측정 19.685 cm = 50/2.54 → DXF 좌표 inch 적발
- 자동 보정 ×2.54 → 17 piece 사이즈 본사 raw 일치 ⭐
- 1벌당 요척: 본사 1.3196 yd vs 우리 (n_lay=4) 1.317 yd — **갭 0.24%** ✅

상세: `docs/history/audits/scale_box_50x50_audit_2026-05-07.md`

---

## 라이선스

내부 도구. 외부 배포 금지.
