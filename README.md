# 원단 요척 산출 시스템

의류 패턴 DXF 파일에서 **원단 소요량(요척)을 자동 계산**하는 웹 앱.

## 주요 기능

- **DXF 파싱** — Optitex, Yuka And Alpha (SuperALPHA_Plus) 등 주요 패턴 CAD 포맷 지원
- **재질 자동 분류** — 피스 메타 / 어노테이션 기반 (주원단 / 심지 / 안감 / 배색 / 주머니감)
- **풀 그레이딩 지원** — 단일 / 복수 / 전체 사이즈 요척 자동 계산
- **50×50 스케일 박스 자동 제외** — 체크용 정사각형은 계산에서 빠짐
- **CP949 한글 인코딩 자동 복원** — SuperALPHA_Plus 파일의 깨진 한글 복구
- **PDF / Excel 리포트 생성** — 사이즈별 × 원단별 요척 표 + 패턴 프리뷰

## 로컬 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

기본 포트: http://localhost:8501

## 기술 스택

- **UI**: Streamlit
- **DXF 처리**: ezdxf
- **기하 연산**: shapely
- **시각화**: matplotlib
- **PDF**: reportlab
- **Excel**: openpyxl

## 파일 구조

```
dxf_test/
├── app.py                    # 메인 Streamlit 앱 (V3)
├── explore_dxf.py            # DXF 파일 탐색 헬퍼
├── extract_pieces.py         # 피스 정보 추출
├── visualize_pieces.py       # 피스 시각화
├── fabric_calculator.py      # 요척 계산 엔진 (CLI 버전)
├── requirements.txt
├── .streamlit/config.toml    # 테마 설정
├── fonts/                    # 한글 폰트 (배포용)
└── output/                   # 생성되는 리포트
```

## 디자인 시스템

**팔레트 (미니멀 모노 + 빨강 강조)**:
- Background: `#ffffff`
- Surface: `#f8fafc`
- Text: `#0f172a`
- Sub-text: `#64748b`
- Border: `#e2e8f0`
- Accent (빨강): `#dc2626` (Primary 버튼 + PDF 타이틀만)

---

© 2026 원단 요척 산출 시스템 · v3.1
