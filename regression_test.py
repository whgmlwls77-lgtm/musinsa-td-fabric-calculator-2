"""MWDLJ2Z01.dxf 회귀 테스트.

Streamlit UI 없이 app.py 의 순수 함수만 호출해
parse → calculate → PDF 생성 파이프라인을 검증한다.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import app  # noqa: E402

DXF_PATH = HERE / "MWDLJ2Z01.dxf"
OUT_DIR = HERE / "output"
OUT_DIR.mkdir(exist_ok=True)

EXPECTED_SIZE_COUNT = 4


def _pass(msg: str) -> None:
    print(f"  [PASS] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")
    sys.exit(1)


def main() -> None:
    assert DXF_PATH.exists(), f"missing {DXF_PATH}"
    dxf_bytes = DXF_PATH.read_bytes()
    print(f"DXF: {DXF_PATH.name} ({len(dxf_bytes):,} bytes)")

    # 1) Parse.
    t0 = time.time()
    parsed = app.parse_dxf_v3(dxf_bytes, DXF_PATH.name)
    dt_parse = time.time() - t0

    if parsed.get("error"):
        _fail(f"parse error: {parsed['error']}")
    _pass(f"parse_dxf_v3 OK ({dt_parse:.2f}s)")

    sizes = parsed["sizes"]
    pieces = parsed["pieces"]
    print(f"  style={parsed['style']!r}  sample_size={parsed['sample_size']!r}")
    print(f"  is_full_grading={parsed['is_full_grading']}  "
          f"detection={parsed['detection_method']}")
    print(f"  sizes={sizes}  pieces={len(pieces)}")

    if not parsed["is_full_grading"]:
        _fail("expected full grading=True")
    if len(sizes) != EXPECTED_SIZE_COUNT:
        _fail(f"expected {EXPECTED_SIZE_COUNT} sizes, got {len(sizes)}: {sizes}")
    _pass(f"full grading with {len(sizes)} sizes")

    # 2) Calculate per-size fabric requirements.
    selected = list(sizes)
    # Default widths per material family (cm) + default efficiency.
    widths: dict[str, float] = {
        "주원단": 150.0,
        "안감": 150.0,
        "심지": 112.0,
        "배색": 150.0,
        "포켓팅": 112.0,
    }
    efficiency = 0.85

    t0 = time.time()
    results_by_size = app.calculate_by_sizes(pieces, selected, widths, efficiency)
    dt_calc = time.time() - t0

    if set(results_by_size.keys()) != set(selected):
        _fail(f"calc keys mismatch: {results_by_size.keys()} vs {selected}")

    for size, rows in results_by_size.items():
        if not rows:
            _fail(f"no fabric rows for size {size}")
        total_yd = sum(r["length_yd"] for r in rows)
        mats = ", ".join(f"{r['name']}:{r['length_yd']:.2f}yd" for r in rows)
        print(f"  size {size}: {len(rows)} mats, total={total_yd:.2f}yd  [{mats}]")
    _pass(f"calculate_by_sizes OK ({dt_calc:.2f}s)")

    # 3) Generate PDF.
    ctx = {
        "style": parsed["style"] or "MWDLJ2Z01",
        "sample_size": parsed["sample_size"],
        "file_name": DXF_PATH.name,
        "generated_at": time.strftime("%Y-%m-%d %H:%M"),
        "selected_sizes": selected,
        "results_by_size": results_by_size,
        "piece_count_by_size": {
            s: sum(1 for p in pieces if p["size"] == s) for s in selected
        },
        "total_piece_entries": len(pieces),
        "efficiency_pct": efficiency * 100,
        "preview_png_bytes": None,
        "ref_size": parsed["sample_size"] or selected[0],
    }
    t0 = time.time()
    pdf_bytes = app.generate_pdf_report_v3(ctx)
    dt_pdf = time.time() - t0

    if not pdf_bytes or len(pdf_bytes) < 10_000:
        _fail(f"PDF too small: {len(pdf_bytes)} bytes")
    if pdf_bytes[:4] != b"%PDF":
        _fail("missing PDF magic bytes")

    out = OUT_DIR / "regression_MWDLJ2Z01.pdf"
    out.write_bytes(pdf_bytes)
    _pass(f"PDF OK ({dt_pdf:.2f}s, {len(pdf_bytes):,} bytes) → {out}")

    print("\nAll regression checks passed.")


if __name__ == "__main__":
    main()
