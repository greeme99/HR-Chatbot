# llama-cpp-python 0.3.34 Windows CPU wheel provenance

조사일: 2026-08-17 KST

## 결론

로드맵 B의 Python 3.12 x86-64 CPU runtime에는 공식 프로젝트가 배포한
`llama_cpp_python-0.3.34-py3-none-win_amd64.whl`을 사용한다. 이 wheel은
CPython 전용 ABI가 아닌 `py3-none-win_amd64` tag이며, package metadata의
`Requires-Python: >=3.8`과 프로젝트의 CPython 3.12 classifier에 부합한다.

## 승인 정보

- 배포자: `abetlen/llama-cpp-python` GitHub Actions
- release: `v0.3.34`
- 파일 크기: 6,591,398 bytes
- SHA-256: `6526fff614e5ef7e439e6369e076a78073e45e1d791dbe1d5e5d42661f46ca1a`
- 라이선스: MIT
- tag commit: `629bd1b333f60d24a01886c5f99019f4c7c3ea6c`
- 검증: GitHub Releases API digest와 로컬 `Get-FileHash -Algorithm SHA256` 결과 일치

PyPI의 0.3.34 배포에는 source distribution만 있으므로 PyPI에서 source build하지
않는다. 공식 CPU wheel index가 가리키는 GitHub release asset만 허용하며, 해시가
다르면 설치를 중단한다.

## 공식 출처

- [v0.3.34 release](https://github.com/abetlen/llama-cpp-python/releases/tag/v0.3.34)
- [CPU wheel index](https://abetlen.github.io/llama-cpp-python/whl/cpu/llama-cpp-python/)
- [설치 안내](https://github.com/abetlen/llama-cpp-python/blob/v0.3.34/README.md)
- [build/release workflow](https://github.com/abetlen/llama-cpp-python/blob/v0.3.34/.github/workflows/build-and-release.yaml)
- [package metadata source](https://github.com/abetlen/llama-cpp-python/blob/v0.3.34/pyproject.toml)
- [MIT license](https://github.com/abetlen/llama-cpp-python/blob/v0.3.34/LICENSE.md)
- [PyPI release JSON](https://pypi.org/pypi/llama-cpp-python/0.3.34/json)
- [verified tag commit](https://github.com/abetlen/llama-cpp-python/commit/629bd1b333f60d24a01886c5f99019f4c7c3ea6c)
