# bin/ — sparrow nesting binaries

이 폴더는 Phase 2 (polygon nesting) 엔진 `sparrow`의 빌드 산출물을 포함한다.
앱 실행 시 `auto_nesting_v2.py`가 platform/arch에 맞는 바이너리를 자동 선택해 호출한다.

## 파일 명명 규칙

```
sparrow-{platform}-{arch}
```

| 파일 | 대상 환경 |
|------|-----------|
| `sparrow-darwin-arm64` | macOS Apple Silicon (M1/M2/M3) — 로컬 개발용 |
| `sparrow-linux-x86_64` | Streamlit Cloud / 일반 Linux 서버 — **배포 시 필요** (별도 빌드) |

## 출처 및 라이선스

- **Upstream**: [JeroenGar/sparrow](https://github.com/JeroenGar/sparrow) — 2D irregular strip packing의 SOTA 알고리즘
- **빌드 의존**: [JeroenGar/jagua-rs](https://github.com/JeroenGar/jagua-rs) — Collision Detection Engine
- **License**: MIT (sparrow), MPL-2.0 (jagua-rs) — 둘 다 상용 사용 가능
- **Paper**:
  - sparrow: "An open-source heuristic to reboot 2D nesting research" (arXiv 2509.13329)
  - jagua-rs: INFORMS Journal on Computing 2024 (DOI 10.1287/ijoc.2024.1025)

## 빌드 방법 (재빌드 필요 시)

### macOS arm64 (현재 포함된 것)

```bash
# 1. Rust toolchain 설치 (한 번만)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env

# 2. sparrow clone + build
git clone --depth 1 https://github.com/JeroenGar/sparrow /tmp/sparrow_build
cd /tmp/sparrow_build
cargo build --release --bin sparrow

# 3. 프로젝트로 복사
cp target/release/sparrow {프로젝트루트}/bin/sparrow-darwin-arm64
chmod +x {프로젝트루트}/bin/sparrow-darwin-arm64
```

빌드 시간: 약 16초 (cargo dependency cache 있을 때). 첫 빌드는 약 30-60초.

### Linux x86_64 (Streamlit Cloud 배포용)

GitHub Actions로 cross-compile 권장. `.github/workflows/build-sparrow.yml` 작성 후 release artifact로 받기.

수동 빌드 시:
```bash
# Docker로 Linux 환경 흉내
docker run --rm -v "$PWD":/work -w /work rust:1.95-slim \
  bash -c "git clone --depth 1 https://github.com/JeroenGar/sparrow /tmp/sparrow && \
           cd /tmp/sparrow && cargo build --release --bin sparrow && \
           cp target/release/sparrow /work/bin/sparrow-linux-x86_64"
```

## 사용된 sparrow 버전 (2026-04-29 기준)

- sparrow: v0.1.0 (commit unknown — git clone --depth 1 사용)
- jagua-rs: v0.7.1 (sparrow의 Cargo.toml 명시)
- Rust toolchain: 1.95.0 (rustc 2026-04-14 빌드)

## CLI 인터페이스

```
sparrow [OPTIONS] --input <INPUT>

Options:
  -i, --input <INPUT>              Path to the input JSON file
  -t, --global-time <GLOBAL_TIME>  Set a global time limit (in seconds)
  -e, --exploration <EXPLORATION>  Set the exploration phase time limit (in seconds)
  -c, --compression <COMPRESSION>  Set the compression phase time limit (in seconds)
  -x, --early-termination          Enable early termination of the optimization process
  -s, --rng-seed <RNG_SEED>        Fixed seed for the random number generator
```

출력은 cwd/output/ 에 `final_{name}.json` + `final_{name}.svg` 로 생성됨.

## 사용 예 (CLI 단독)

```bash
./sparrow-darwin-arm64 -i input.json -t 30 -x
```

`auto_nesting_v2.py`가 자동으로 호출하므로 일반적으로 직접 실행할 필요 없음.
