# HR RAG 로컬 프로토타입 구현 옵션 조사

- 기준일: 2026-08-17 (KST)
- 범위: HR 평가 담당자용 Streamlit 탭 기반 로컬 프로토타입
- 제약: Windows, i7-7700HQ, RAM 약 8GB, GTX 1050 Ti 4GB, Python 3.12, 텍스트 PDF 10개·DOCX 5개·FAQ 약 200건
- 근거 정책: 공식 문서, 공식 저장소, 공식 모델 카드만 사용

## 결론

첫 구현은 다음 조합을 권장한다.

1. **UI:** Streamlit의 `st.tabs`로 `채팅 검증 / 문서 현황 / 평가 결과` 3개 탭을 만든다. 모델, 임베더, DB 연결은 `st.cache_resource`로 한 번만 적재하고, 최근 5개 대화만 `st.session_state`에 둔다.
2. **LLM 런타임:** Windows 네이티브 **Ollama**를 독립 프로세스로 사용하고 앱은 localhost API만 호출한다. 기본 생성 모델은 **Qwen3 1.7B Q4_K_M**, 비사고 모드(`/no_think`)와 짧은 출력 제한으로 시작한다.
3. **임베딩:** 기본은 **`intfloat/multilingual-e5-small`**을 `sentence-transformers`로 로컬 실행한다. 검색 게이트가 미달일 때만 **BGE-M3**를 비교한다.
4. **저장/검색:** 별도 벡터 DB 없이 **SQLite + FTS5 + NumPy exact cosine**으로 시작한다. 승인된 인덱스 버전만 조회하고, dense 상위 결과와 FTS5 결과를 결합한다. 현재 문서량에서 먼저 실제 지연을 계측하고 필요할 때만 전용 인덱스를 추가한다.
5. **파싱:** 텍스트 PDF는 **pdfplumber**, DOCX는 **python-docx**, FAQ는 승인된 CSV/JSON/HTML 스냅샷으로 처리한다. 표는 행·열 관계를 보존한 Markdown과 평문을 함께 저장한다. OCR과 이미지 설명은 범위 밖이다.
6. **구조:** Streamlit 코드에서 검색·생성·평가를 분리한 작은 Python 서비스 계층을 둔다. 이후 동일한 요청/응답 DTO를 FastAPI에 노출하고 저장소 구현만 PostgreSQL + pgvector로 교체한다. 프로토타입에 LangChain, Chroma, 관리용 CMS를 선제 도입하지 않는다.

이 권고는 모델 품질을 보장한다는 뜻이 아니다. 1.7B 모델이 HR 수치·예외 조건에서 85% 생성 정확도와 중대 오류 0건을 달성할지는 반드시 100문항 평가로 확인해야 한다. 미달 시 검색과 생성을 분리해 진단하고, 생성만 사내 GPU 서버의 7B~8B급 모델로 교체한다.

## 1. Streamlit 탭과 세션

### 공식 기능에서 확인된 점

- [`st.tabs`](https://docs.streamlit.io/develop/api-reference/layout/st.tabs)는 여러 컨테이너를 탭으로 묶는다. 기본 설정에서는 선택하지 않은 탭도 모두 계산한다. 최신 API의 `on_change="rerun"`과 각 탭의 `.open`을 사용하면 선택된 탭만 조건부 렌더링할 수 있다.
- [`st.session_state`](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state)는 사용자 세션별로 rerun 사이의 값을 유지한다. 따라서 최근 5개 대화와 현재 필터는 여기에 두되 영속 로그 저장소로 사용하지 않는다.
- [`st.cache_resource`](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_resource)는 DB 연결이나 ML 모델 같은 리소스를 캐시한다. 전역 캐시는 모든 사용자와 rerun이 공유되므로 객체가 thread-safe해야 한다.
- [`st.testing.v1.AppTest`](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest)는 브라우저 없이 위젯과 출력, 세션 상태를 조작·검사할 수 있다.

### 탭별 최소 기능

| 탭 | 최소 기능 | 비고 |
|---|---|---|
| 채팅 검증 | 답변, 출처 링크·페이지/조항·인용 일부, 검색 Top 5, 단계별 지연, 도움 됨/안 됨 및 의견 | 내부 프롬프트는 표시하지 않음 |
| 문서 현황 | 문서 목록, 메타데이터 오류, 파싱/색인 상태, 후보 버전 승인, 승인 버전 되돌리기 | 문서 본문 편집 CMS는 제외 |
| 평가 결과 | 평가 CSV 실행, retrieval hit@5, 생성 채점 입력, 거절률, 중대 오류, 실패 원인, 결과 CSV 내보내기 | 자동 튜닝 제외 |

탭 전환 때 평가 전체 실행이나 모델 적재가 다시 발생하지 않도록 무거운 작업은 버튼 제출 뒤 실행하고 결과 ID만 세션에 둔다. LLM 호출은 Ollama 프로세스가 소유하므로 Streamlit 전역 캐시에 생성 모델 자체를 올리지 않아도 된다.

## 2. 로컬 LLM 런타임

| 선택지 | 공식 확인 사항 | 판단 |
|---|---|---|
| Ollama | [Windows 문서](https://github.com/ollama/ollama/blob/main/docs/windows.mdx)에 따르면 Windows 네이티브 앱, NVIDIA/AMD 지원, 기본 API `localhost:11434`를 제공한다. [API 문서](https://docs.ollama.com/api/introduction)는 로컬 API와 공식 Python 라이브러리를 제공하지만 API가 엄격한 버전 체계는 아니라고 명시한다. | **기본 선택.** 설치·API 연결이 가장 단순하다. 실행 파일·모델 digest를 기록해야 한다. |
| llama.cpp | [공식 저장소](https://github.com/ggml-org/llama.cpp)는 Windows 사전 빌드, GGUF, CUDA/Vulkan/CPU 백엔드, OpenAI 호환 `llama-server`를 제공한다. [Windows 빌드 문서](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md)는 CUDA/Vulkan 빌드 방법을 설명한다. | 재현 가능한 단일 GGUF와 세부 성능 조절이 필요할 때의 **대안/벤치마크 런타임**. 초기 UX는 Ollama보다 수동 설정이 많다. |

GTX 1050 Ti는 Ollama의 [하드웨어 지원 표](https://docs.ollama.com/gpu)에 compute capability 6.1 지원 카드로 명시되어 있다. 다만 5.0~6.2 세대는 NVIDIA 드라이버 570 이상이 필요하므로 설치 전 드라이버를 확인해야 한다. 4GB VRAM에서는 모델 전체와 큰 KV cache가 동시에 올라가지 않을 수 있으므로 실제 GPU offload, RAM 사용량, tokens/s를 기록한다.

보안상 서버는 localhost에만 유지한다. 모델 다운로드는 승인된 PC에서 한 번 수행한 뒤 모델명, 런타임 버전, 파일/digest, 라이선스를 manifest에 고정한다. 자동 업데이트가 재현성을 흔들 수 있으므로 평가 실행마다 런타임과 모델 식별자를 결과에 저장한다.

## 3. 1B~3B 한국어 가능 instruct 모델

| 모델 | 공식 모델 카드의 사실 | 라이선스 | 용도/판단 |
|---|---|---|---|
| [Qwen3 1.7B](https://huggingface.co/Qwen/Qwen3-1.7B) | 1.7B, 100개 이상 언어·방언, 32K context, thinking/non-thinking 전환, Ollama와 llama.cpp 지원 | Apache-2.0 | **기본 후보.** 품질/크기/라이선스 균형이 가장 좋다. HR 답변은 비사고 모드와 낮은 출력 길이로 지연을 줄인다. |
| [Qwen3 0.6B](https://huggingface.co/Qwen/Qwen3-0.6B) | 동일 계열의 0.6B 다국어 모델 | Apache-2.0 | 파이프라인 smoke test와 하한 비교용. 정책 답변 운영 후보로 보지 않는다. |
| [Gemma 3 1B IT](https://huggingface.co/google/gemma-3-1b-it) | 140개 이상 언어, 128K context의 instruction-tuned 모델 | Gemma terms, gated access | 비교 후보. 별도 약관 검토와 접근 승인이 필요해 기본 후보보다 조달이 복잡하다. |
| [Kanana Nano 2.1B Instruct](https://huggingface.co/kakaocorp/kanana-nano-2.1b-instruct) | 한국어·영어 이중언어 모델이며 한국어 성능을 목표로 함 | CC-BY-NC-4.0 | 한국어 품질 비교에는 유용하나 **사내 업무 사용은 상업적 이용 해석을 법무가 승인하기 전 채택하지 않는다.** |

Ollama의 [공식 Qwen3 1.7B 배포](https://ollama.com/library/qwen3%3A1.7b)는 Q4_K_M, 약 1.4GB로 표시된다. 실제 메모리에는 weights 외 KV cache와 런타임 버퍼도 필요하므로 파일 크기를 총 메모리로 간주하면 안 된다. 권장 초기 설정은 Qwen3 1.7B, 짧은 context(검색 근거 Top 5 중 필요한 부분만), 최대 답변 토큰 제한, `/no_think`이다.

모델 선정은 100문항으로 동일한 retrieval context를 주고 비교한다. 생성 모델이 근거를 만들지 못하게 `답변/인용 chunk_id/거절 사유` 구조를 강제하고, 인용 chunk가 실제 검색 결과에 있는지는 코드로 검증한다. 존재하지 않는 수치·규정, 잘못된 출처, 개인 데이터 조회 가장, 근거 없는 확정 답변은 한 건이라도 전체 실패다.

## 4. 임베딩 모델

| 모델 | 공식 모델 카드의 사실 | 라이선스 | 판단 |
|---|---|---|---|
| [`intfloat/multilingual-e5-small`](https://huggingface.co/intfloat/multilingual-e5-small) | 384차원 계열, 모델 weight 약 471MB, 100개 언어 지원(저자도 저자원 언어 성능 저하 가능성을 경고) | MIT | **기본 후보.** 8GB RAM에서 비교적 작고 Python 3.12로 직접 실행하기 쉽다. 문서에는 `passage:`, 질문에는 `query:` prefix를 모델 카드 지침대로 적용한다. |
| [`BAAI/bge-m3`](https://huggingface.co/BAAI/bge-m3) | 1024차원, 최대 8192 tokens, dense/sparse/multi-vector와 다국어 지원 | MIT | retrieval hit@5가 90% 미달일 때 비교할 상향 후보. 모델과 벡터가 더 커 현재 PC 비용이 높다. |

먼저 E5-small dense 검색과 FTS5 lexical 검색을 각각 평가하고 결합한다. 모델 변경 시 기존 벡터를 혼용하지 말고 `embedding_model_id`, revision, dimension, normalization을 인덱스 버전에 저장해 전량 재색인한다. Ollama의 [embedding 문서](https://docs.ollama.com/capabilities/embeddings)도 색인과 질의에 동일 모델을 사용하라고 명시한다.

## 5. 로컬 벡터 저장소

| 선택지 | 장점 | 제약과 판단 |
|---|---|---|
| SQLite + FTS5 + NumPy exact cosine | Python 3.12 표준 `sqlite3`, 단일 파일, 문서 승인·버전·평가 결과와 벡터를 한 트랜잭션 모델로 관리 가능. [SQLite FTS5](https://www.sqlite.org/fts5.html)는 full-text 검색과 relevance rank를 제공한다. | **권장.** chunk 수와 exact scan 지연을 실제 측정한다. 벡터는 float32 BLOB로 저장하고 시작 시 승인 인덱스만 행렬로 캐시한다. |
| Chroma | [공식 저장소](https://github.com/chroma-core/chroma)는 in-memory 시작, persistence, metadata filter, add/update/delete/query API를 제공한다. Apache-2.0. | 빠른 데모에는 편하지만 현재 규모에 별도 추상·의존성이 추가된다. 운영 pgvector 전환성도 plain SQL schema보다 직접적이지 않다. 2순위. |
| FAISS | [공식 설치 문서](https://github.com/facebookresearch/faiss/blob/main/INSTALL.md)는 Windows x86-64 CPU를 지원하지만 공식 Python 배포 경로는 conda이며 Windows GPU 패키지는 아니다. MIT. | Python 3.12 `venv` 우선 결정과 충돌한다. 검색량이 커져 exact scan이 병목임이 입증된 뒤 고려한다. |
| sqlite-vec | [공식 저장소](https://github.com/asg017/sqlite-vec)는 Windows 포함 SQLite가 실행되는 곳에서 동작하고 Python 패키지를 제공한다. | 공식 문서가 **pre-v1, breaking changes 예상**이라고 경고한다. MVP의 승인/되돌리기 기반을 여기에 묶지 않는다. 실험 옵션만 유지한다. |

권장 SQLite 스키마의 최소 개념은 다음과 같다.

- `documents`: 안정적 문서 ID, 제목, 원본 URI, 우선순위, 시행일/만료일, checksum
- `chunks`: 안정적 chunk ID, 문서 ID, 페이지/조항/표 위치, text, embedding
- `index_versions`: 모델·revision·chunking 설정·생성 시각·상태(`candidate`, `approved`, `retired`)
- `ingestion_runs`: 파일별 성공/실패와 오류
- `evaluation_runs/results`: 데이터셋 checksum, 모델/digest, retrieval/generation 설정, 질문별 결과
- `feedback`: 질문·답변·인용 묶음, 평가자 의견; 30일 보존 정책 대상

검색 SQL에는 반드시 `index_version.status='approved'`, 문서 공개 등급, 시행/만료 조건을 적용한다. 새 색인은 별도 candidate 버전으로 완성·평가한 후 단일 승인 포인터만 전환하며, 되돌리기는 이전 승인 버전으로 포인터를 바꾸는 방식으로 한다.

## 6. PDF, DOCX, 표 파싱

### 권장 경량 경로

- [pdfplumber](https://github.com/jsvine/pdfplumber)는 문자·텍스트·표 추출과 시각 디버깅을 제공하고, 공식 README가 machine-generated PDF에 가장 적합하다고 명시한다. MIT이며 Python 3.12를 테스트한다. 현재의 “텍스트 선택 가능한 PDF만” 조건과 맞는다.
- [python-docx](https://github.com/python-openxml/python-docx)와 [공식 table 문서](https://python-docx.readthedocs.io/en/latest/user/tables.html)로 문단과 표를 문서 순서대로 읽는다. 병합 셀과 비균일 표는 일반 2차원 행렬처럼 보이지 않을 수 있으므로 원본 XML 위치와 사람이 읽을 Markdown을 함께 보존한다.
- FAQ 스냅샷은 안정적 `faq_id`, 질문, 승인 답변, category, source_uri, effective dates를 갖는 CSV 또는 JSON으로 정규화한다. HTML은 허용된 컨테이너에서만 텍스트·링크를 추출하고 스크립트는 실행하지 않는다.

각 chunk는 `document_id`, `page`, `section`, `table_id`, `source_uri`, `effective_from`, `expires_at`, `priority`, `checksum`을 유지한다. 표는 셀을 무작정 이어 붙이지 말고 표 제목/열 머리글/행 머리글을 각 데이터 행에 반복한 검색용 텍스트와 원형에 가까운 Markdown을 함께 저장한다. 인용은 chunk 텍스트가 아니라 원본 페이지/조항과 원본 링크를 가리킨다.

### 상향 옵션

[Docling 공식 저장소](https://github.com/docling-project/docling)는 PDF/DOCX, reading order, table structure, lossless JSON/Markdown, 민감·air-gapped 환경의 로컬 실행을 지원하며 MIT이다. [지원 형식 문서](https://github.com/docling-project/docling/blob/main/docs/usage/supported_formats.md)는 RAG용 chunks JSONL도 제공한다. 그러나 모델 기반 PDF 파이프라인은 초기 다운로드와 더 큰 런타임 비용이 있으므로, 경량 파서의 표 회귀 샘플이 기준 미달일 때만 상향 비교한다. OCR은 이번 MVP 범위에 넣지 않는다.

파서별 골든 샘플을 둔다: 일반 본문, 다단 문서, 페이지 경계, 표, 병합 셀, 머리말/꼬리말. 문서별 추출 미리보기와 오류를 “문서 현황” 탭에서 HR 담당자가 승인하기 전에는 색인 후보로도 공개하지 않는다.

## 7. FastAPI + PostgreSQL + pgvector 전환

Streamlit 이벤트 안에 RAG 로직을 작성하지 않고 다음 경계를 유지한다.

```text
UI -> ChatService -> Retriever interface -> SQLiteRetriever
                  -> Generator interface -> OllamaGenerator
   -> IngestionService -> Parser interface
   -> EvaluationService
```

요청/응답은 처음부터 평범한 typed DTO로 둔다: `ChatRequest(question, conversation_context, index_version)`와 `ChatResponse(answer, citations, refusal, timings, config_id)`. 이후 FastAPI route는 이 서비스를 호출만 한다. [FastAPI 공식 기능 문서](https://fastapi.tiangolo.com/features/)와 [request body 문서](https://fastapi.tiangolo.com/tutorial/body/)처럼 Pydantic 모델을 사용하면 입력 검증과 OpenAPI schema를 얻을 수 있다.

운영 저장소는 `PostgresRetriever` 구현으로 교체한다. [pgvector 공식 저장소](https://github.com/pgvector/pgvector)는 vector column, cosine/L2/inner-product 검색, exact nearest-neighbor 기본값, HNSW/IVFFlat 근사 인덱스, 일반 `WHERE` filter 결합을 지원한다. 프로토타입의 안정적 ID와 메타데이터 열을 그대로 옮기고 embedding을 재생성하지 않아도 되도록 모델 ID와 dimension을 명시한다.

초기 운영 데이터에서도 정확 검색으로 시작하고 지연 측정 후 HNSW를 추가한다. pgvector는 근사 인덱스가 속도를 위해 recall을 교환한다고 명시하므로 retrieval hit@5 게이트를 다시 실행해야 한다. 승인 등급이나 테넌트 filter와 근사 검색을 결합할 때 결과 수와 recall이 달라질 수 있다는 [pgvector filtering 문서](https://github.com/pgvector/pgvector#filtering)도 고려한다.

이 구조에서는 Streamlit을 폐기하지 않고 HR 내부 평가 클라이언트로 유지하면서, 임직원용 Next.js가 FastAPI를 호출하도록 확장할 수 있다. Google Workspace SSO와 Google Group 역할 매핑은 운영 API의 인증 경계에서 추가하고 프로토타입에는 가짜 로그인이나 별도 비밀번호 저장소를 만들지 않는다.

## 8. 정확도 향상을 위한 실험 순서

1. 파서 골든 샘플을 통과시키고 문서/페이지/조항/표 metadata 누락을 먼저 제거한다.
2. 답변 가능 70개, 거절 30개의 평가 CSV를 고정하고 파일 checksum을 저장한다.
3. E5-small dense 단독의 hit@5, FTS5 단독의 hit@5, 둘의 결합 hit@5를 비교한다.
4. chunk 크기/overlap보다 먼저 문서 제목·조항 제목·표 머리글을 검색 텍스트에 포함했을 때를 비교한다.
5. retrieval hit@5 90% 미달이면 실패 질문을 `파싱 / chunk / 어휘 / 의미 검색 / metadata filter`로 분류한다. 그 뒤에만 BGE-M3나 reranker를 비교한다.
6. 동일한 retrieval context로 Qwen3 1.7B를 평가하고 HR 담당자가 정답성·근거성·안전성을 2차 판정한다.
7. 거절 threshold는 30개 OOD 질문으로 별도 보정한다. 평균 정확도와 중대 오류 0건 게이트를 분리한다.
8. 워밍업 후 질문 제출부터 답변·출처 표시 완료까지를 측정하고 median 5초를 판정한다. 검색/프롬프트/첫 토큰/완료 시간을 따로 기록한다.

LangChain은 위 실험에 필수 기능이 확인될 때 추가한다. 현재 필요한 파싱, embedding 호출, cosine 검색, Ollama HTTP 호출, 평가 집계는 작은 명시적 모듈로 구현 가능하며, 프레임워크 추상화가 모델·chunk·threshold별 원인을 가리지 않도록 한다.

## 9. 주요 위험과 대응

| 위험 | 영향 | 대응/게이트 |
|---|---|---|
| 1.7B 생성 품질 한계 | 정확도 85% 또는 중대 오류 0건 실패 | retrieval context를 고정해 생성만 비교; 미달 시 사내 7B~8B 런타임으로 교체 |
| GTX 1050 Ti 구형 드라이버·4GB VRAM | CPU fallback, 5초 초과, 메모리 부족 | NVIDIA 570+ 확인, Q4 모델·짧은 context, GPU offload와 tokens/s 기록 |
| 표 추출 오류 | 휴가 일수·금액이 잘못 검색됨 | 표 골든 샘플, HR 추출 미리보기 승인, 표 머리글 반복 chunk |
| 다국어 embedding의 한국어 도메인 성능 미확인 | hit@5 90% 미달 | E5-small/FTS5/결합을 분리 측정, 그 뒤 BGE-M3 비교 |
| 라이선스 부적합 | 사내 사용 중단 | Apache/MIT 우선; Kanana NC 및 Gemma terms는 법무 승인 전 제외 |
| Ollama API/자동 업데이트 | 재현 실패 | 런타임 버전·모델 digest·설정·dataset checksum 저장, 승인된 설치물만 반입 |
| 세션/로그에 개인정보 잔류 | 개인정보 노출 | 최근 5턴은 session only, 저장 전 민감 패턴 마스킹, 원문 30일 삭제, 가명 ID |
| candidate 문서가 검색됨 | 미승인 정책 노출 | 조회 계층에서 approved index predicate 강제, 승인/rollback 통합 테스트 |
| 향후 DB 전환 때 의미 변화 | retrieval 회귀 | cosine 정규화·tie-break·filter 계약을 테스트로 고정하고 pgvector 전환 후 동일 평가 재실행 |

## 10. 구현 시 고정할 manifest

재현 가능한 평가 결과마다 다음을 저장한다.

- Git commit, Python 및 의존성 lockfile
- OS/GPU/driver, Ollama 또는 llama.cpp 버전
- 생성 모델 이름, 원본 revision/digest, GGUF quantization, license
- embedding 모델 revision, dimension, prefix, normalization
- parser 버전과 문서별 SHA-256
- chunking 설정, retrieval Top K, lexical/dense 결합 방식, 거절 threshold
- index version, evaluation dataset checksum, KST 실행 시각
- retrieval/generation/refusal 지표와 질문별 결과 CSV

## 공식 출처 목록

- Streamlit: [`st.tabs`](https://docs.streamlit.io/develop/api-reference/layout/st.tabs), [`st.session_state`](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state), [`st.cache_resource`](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_resource), [`AppTest`](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest)
- Ollama: [Windows](https://github.com/ollama/ollama/blob/main/docs/windows.mdx), [API](https://docs.ollama.com/api/introduction), [hardware](https://docs.ollama.com/gpu), [embeddings](https://docs.ollama.com/capabilities/embeddings), [Qwen3 1.7B package](https://ollama.com/library/qwen3%3A1.7b)
- llama.cpp: [repository](https://github.com/ggml-org/llama.cpp), [build guide](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md)
- 모델 카드: [Qwen3 1.7B](https://huggingface.co/Qwen/Qwen3-1.7B), [Qwen3 0.6B](https://huggingface.co/Qwen/Qwen3-0.6B), [Gemma 3 1B IT](https://huggingface.co/google/gemma-3-1b-it), [Kanana Nano 2.1B Instruct](https://huggingface.co/kakaocorp/kanana-nano-2.1b-instruct)
- 임베딩 카드: [multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small), [BGE-M3](https://huggingface.co/BAAI/bge-m3)
- 저장소: [SQLite FTS5](https://www.sqlite.org/fts5.html), [Chroma](https://github.com/chroma-core/chroma), [FAISS install](https://github.com/facebookresearch/faiss/blob/main/INSTALL.md), [sqlite-vec](https://github.com/asg017/sqlite-vec), [pgvector](https://github.com/pgvector/pgvector)
- 파서: [pdfplumber](https://github.com/jsvine/pdfplumber), [python-docx](https://github.com/python-openxml/python-docx), [python-docx tables](https://python-docx.readthedocs.io/en/latest/user/tables.html), [Docling](https://github.com/docling-project/docling), [Docling formats](https://github.com/docling-project/docling/blob/main/docs/usage/supported_formats.md)
- API: [FastAPI features](https://fastapi.tiangolo.com/features/), [FastAPI request body](https://fastapi.tiangolo.com/tutorial/body/)

## 부록 A. 외부 클라우드 API 없는 FastAPI + 전용 Vector DB 구성

### A.1 요구의 해석과 가능 여부

여기서 “외부 API 연결 없음”은 **외부 클라우드 LLM·embedding·Vector DB API를 호출하지 않는다**는 뜻으로 해석한다. FastAPI는 같은 PC의 localhost 또는 사내망 안에서만 제공하는 내부 API다. 이 조건에서도 전체 RAG 흐름은 구현 가능하다.

```text
HR 평가 UI 또는 향후 Next.js
        |
        | localhost HTTP 또는 사내 HTTPS
        v
FastAPI (입력 검증, 인증/권한, 응답 계약, 감사 로그)
        |
        +--> 로컬 sentence-transformers --> query embedding
        |
        +--> 로컬 PostgreSQL + pgvector --> 승인 chunk Top 5
        |
        +--> 로컬 Ollama --> 근거 제한 답변
        |
        `--> 답변의 citation ID를 검색 결과와 코드로 대조
```

색인 경로도 로컬이다.

```text
data/inbox의 승인 후보 PDF/DOCX/FAQ
  -> 로컬 parser
  -> HR 추출 미리보기
  -> 로컬 embedding
  -> candidate index
  -> 평가 게이트
  -> approved 전환
```

Ollama의 [Windows 문서](https://github.com/ollama/ollama/blob/main/docs/windows.mdx)와 [API 문서](https://docs.ollama.com/api/introduction)는 Windows 네이티브 실행과 기본 localhost API를 제공한다. `sentence-transformers` 모델 파일과 생성 GGUF를 사전 반입하면 추론 시 인터넷이 필요하지 않다. 다만 “로컬 실행”과 “네트워크 차단”은 같은 말이 아니다. 운영 설정에서 cloud client를 사용하지 않고, 방화벽/프록시 정책으로 프로세스의 외부 egress를 막으며, 필요한 모델 artifact를 checksum으로 사전 반입해야 완전 로컬 경계가 성립한다.

### A.2 전용 Vector DB 선택: Chroma 대 PostgreSQL + pgvector

사용자가 전용 Vector DB 사용을 요구한다면, **하나를 골라 프로토타입에서 운영까지 이어가는 기본값은 PostgreSQL + pgvector**를 권장한다. 현재 약 215개 원본 문서만 놓고 보면 두 제품 모두 용량상 충분하고 vector 성능이 선택을 좌우하지 않는다. 승인·되돌리기, 시행일, 문서 우선순위, 로그 보존, 향후 사용자/세션과 한 트랜잭션 체계에서 다룰 수 있는지가 더 중요하다.

| 기준 | Chroma | PostgreSQL + pgvector |
|---|---|---|
| 로컬 시작 | [공식 Python reference](https://docs.trychroma.com/reference/python)는 `PersistentClient(path=...)`를 제공한다. 별도 DB 서버 없이 가장 빨리 시작한다. | PostgreSQL 서비스와 `CREATE EXTENSION vector`가 필요하다. [pgvector 공식 저장소](https://github.com/pgvector/pgvector)는 Windows 빌드, Docker, conda-forge 설치 경로를 제공한다. |
| 공식 용도 표현 | 공식 reference는 PersistentClient를 **local development and testing** 용도로 설명하고 production에는 server-backed Chroma를 선호하라고 한다. | pgvector는 vector를 일반 PostgreSQL 데이터와 함께 저장하며 ACID, WAL, point-in-time recovery, JOIN을 그대로 사용한다고 명시한다. |
| 검색 | collection query와 metadata filter가 간단하다. | cosine/L2/inner product, exact 기본 검색, HNSW/IVFFlat, SQL `WHERE` filter를 지원한다. 현재 규모에서는 exact 검색부터 사용 가능하다. |
| 문서 승인/버전/로그 | collection/metadata로 구현 가능하지만 관계형 승인 이력과 앱 로그는 별도 저장소가 필요해질 수 있다. | documents, chunks, index_versions, evaluation_runs, feedback를 FK·transaction으로 함께 관리하기 쉽다. |
| FastAPI 연결 | in-process PersistentClient 또는 별도 Chroma HTTP server. [client-server 문서](https://docs.trychroma.com/docs/run-chroma/client-server)는 localhost server와 `HttpClient`를 제공한다. | 표준 PostgreSQL Python driver/pool로 FastAPI가 직접 연결한다. DB port를 외부에 공개할 이유가 없다. |
| 보안 경계 | 현재 [서버 설정 문서](https://docs.trychroma.com/reference/server-env-vars)는 기본 listen address가 `0.0.0.0`이고 Chroma v1.0이 built-in auth 구현을 더 이상 제공하지 않는다고 명시한다. 별도 proxy/auth와 bind 제한이 필요하다. | PostgreSQL 자체 계정·권한·네트워크 정책을 사용하고 FastAPI 서비스 계정에 필요한 table 권한만 줄 수 있다. |
| 운영 전환 | 빠른 단일 PC 실험에는 좋지만 PostgreSQL로 옮기면 collection/metadata와 승인 이력을 이관·재검증해야 한다. | 최초 설치는 무겁지만 예정된 운영 스택과 동일해 데이터 이전을 피한다. |

따라서 선택은 다음처럼 정리한다.

- **이번 요구처럼 FastAPI와 전용 DB를 처음부터 명시하고 향후 사내 운영까지 고려:** PostgreSQL + pgvector.
- **1~2일짜리 폐기 가능한 검색 실험이고 PostgreSQL 설치가 당장 막힘:** Chroma PersistentClient. 이것은 임시 선택임을 manifest에 남기고, 승인/평가 원장은 SQLite 또는 CSV로 분리한다.
- **Chroma를 사내 서버로 계속 운영:** FastAPI만 외부 요청을 받고 Chroma는 loopback/private network에 숨긴다. 현재 Chroma v1 서버에 built-in auth가 없다는 공식 경고 때문에 Chroma port를 임직원 브라우저에 직접 공개하지 않는다.

PostgreSQL + pgvector에서도 이 문서량에는 HNSW가 필수가 아니다. [pgvector 문서](https://github.com/pgvector/pgvector#querying)는 exact nearest-neighbor가 기본이고 근사 인덱스는 recall을 속도와 교환한다고 설명한다. 먼저 exact cosine으로 retrieval hit@5와 지연을 기준화한 후에만 HNSW를 추가하고 전체 100문항을 재실행한다.

### A.3 로컬 FastAPI 호출 흐름

권장 최소 endpoint는 다음뿐이다.

| Endpoint | 주체 | 동작 |
|---|---|---|
| `POST /v1/chat` | HR 평가자 | 질문 검증 → 로컬 embedding → approved 문서 검색 → 로컬 LLM → citation 대조 → 응답 |
| `POST /v1/evaluations` | HR 관리자 | 고정 CSV 평가 실행을 생성; 긴 실행은 run ID 반환 |
| `GET /v1/evaluations/{id}` | HR 평가자 | 지표·질문별 실패 결과 조회 |
| `POST /v1/indexes` | HR 관리자 | inbox를 candidate로 파싱·색인 |
| `POST /v1/indexes/{id}/approve` | HR 관리자 | 게이트 통과 candidate를 승인 포인터로 전환 |
| `POST /v1/indexes/{id}/rollback` | HR 관리자 | 이전 승인 버전으로 포인터 전환 |

요청 순서는 다음과 같다.

1. FastAPI의 Pydantic request model이 질문 길이·형식과 index ID를 검증한다. [FastAPI request body 문서](https://fastapi.tiangolo.com/tutorial/body/)는 모델 기반 검증과 JSON Schema/OpenAPI 생성을 설명한다.
2. 인증된 주체와 역할을 확인한다. 프로토타입 localhost 단일 평가자라면 OS 사용자 경계를 쓰되, 사내망으로 열 때는 Google Workspace OIDC와 Google Group의 `hr_admin` 매핑을 FastAPI 또는 신뢰할 수 있는 인증 proxy에서 강제한다.
3. 민감 패턴을 마스킹한 후 request ID와 가명 사용자 ID만 로그 context에 둔다.
4. 로컬 embedder가 query vector를 만들고 pgvector가 `approved`, 공개 등급, 시행/만료 predicate를 포함한 exact Top 5를 반환한다.
5. Generator adapter가 로컬 Ollama에 필요한 chunk만 전달한다. Ollama port는 FastAPI host에서만 접근 가능하게 유지한다.
6. 반환된 citation ID가 Top 5 안에 없거나 근거 threshold 미달이면 생성 답변을 폐기하고 안전 거절한다.
7. 단계별 시간과 model/index/config ID를 응답 및 평가 원장에 남긴다. 질문·답변 원문은 확정된 30일 정책을 적용한다.

FastAPI의 목적은 외부 서비스를 호출하는 것이 아니라 **클라이언트와 로컬 AI/DB 사이에 안정적인 신뢰 경계와 계약을 두는 것**이다. Streamlit이 서버 측 Python에서 FastAPI를 호출하면 브라우저 CORS는 발생하지 않는다. 향후 Next.js 브라우저가 다른 origin에서 직접 호출한다면 [FastAPI CORS 문서](https://fastapi.tiangolo.com/tutorial/cors/)에 따라 정확한 사내 origin만 허용한다. credential을 사용할 때 wildcard origin에 의존하지 않는다.

### A.4 보안 경계

#### 단일 PC 프로토타입

- FastAPI/Uvicorn은 `127.0.0.1`에만 bind한다. LAN 전체에 여는 `0.0.0.0`을 사용하지 않는다.
- PostgreSQL, Ollama, Chroma를 쓴다면 Chroma도 loopback에만 bind하고 Windows Firewall inbound rule로 막는다.
- Streamlit만 FastAPI를 호출하며 DB와 Ollama credential/port를 브라우저에 전달하지 않는다.
- Swagger/ReDoc는 개발 중 localhost에만 두고 사내망 운영에서는 비활성화하거나 관리자에게만 제한한다.
- model/embedding 다운로드 기능을 앱 endpoint로 제공하지 않는다. 승인된 artifact만 별도 반입한다.

#### 사내망 운영

- 브라우저에 노출되는 진입점은 TLS termination proxy 하나로 제한한다. [FastAPI HTTPS 문서](https://fastapi.tiangolo.com/deployment/https/)는 TLS proxy가 HTTPS를 처리하고 내부 FastAPI에 전달하는 일반 구성을 설명한다.
- FastAPI는 private subnet/loopback에 두고 proxy IP에서 온 forwarded header만 신뢰한다. wildcard proxy trust는 네트워크가 실제로 proxy에만 닫혀 있을 때도 신중히 사용한다.
- 명시적 allowed host와 allowed CORS origin을 설정한다. FastAPI가 제공하는 [TrustedHostMiddleware 안내](https://fastapi.tiangolo.com/advanced/middleware/)로 Host header 공격을 제한할 수 있다.
- employee와 hr_admin endpoint 권한을 분리하고, 문서 승인·rollback은 hr_admin만 허용한다.
- DB는 FastAPI 서비스 계정에 최소 권한만 부여하고 외부 listen/firewall을 닫는다. ingestion 계정과 read-only chat 계정을 분리하는 것이 바람직하다.
- rate limit, request body 제한, timeout은 진입 proxy와 앱 양쪽에 둔다. 프롬프트나 검색 원문이 일반 access log에 남지 않도록 logging filter를 적용한다.
- 외부 egress 차단을 네트워크 정책으로 검증한다. “코드에서 클라우드 client를 호출하지 않음”만으로 반출 방지가 증명되지는 않는다.

### A.5 FastAPI와 직접 Python 호출의 차이

| 항목 | Streamlit → Python service 직접 호출 | Streamlit/Next.js → FastAPI |
|---|---|---|
| 프로세스 | UI와 RAG가 같은 Python 프로세스 | HTTP API 프로세스로 분리 가능 |
| 초기 복잡도 | 가장 낮고 디버깅이 단순 | 서버 lifecycle, port, DTO serialization, timeout, health check 필요 |
| 지연 | HTTP 직렬화/loopback 비용 없음 | 작은 HTTP overhead 추가. 전체 지연은 보통 로컬 LLM이 지배하지만 반드시 계측 |
| 보안 면 | 네트워크 endpoint가 없어 공격면이 작음 | 인증·권한·rate limit·TLS/CORS/host 검증이 필요하지만 중앙 정책을 강제 가능 |
| 클라이언트 | Python UI에 결합 | Next.js, Streamlit, 평가 runner 등 여러 클라이언트가 동일 계약 사용 |
| 독립 확장/교체 | UI와 AI 배포 주기가 묶임 | UI, API, Ollama, DB를 독립 운영 가능 |
| 테스트 | service unit test가 빠름 | 동일 unit test + API contract/integration test 필요 |
| 장애 격리 | UI rerun이 리소스 lifecycle에 영향 | API가 model/DB pool을 안정적으로 소유 가능 |

따라서 **정확도 검증만 하는 단일 PC 폐기형 프로토타입**에는 직접 Python 호출이 더 단순하다. 하지만 사용자가 FastAPI를 명시했고 향후 Next.js·Google Workspace SSO·사내망 다중 사용자를 계획하므로, 이번에는 다음 절충을 권장한다.

1. retrieval/generation/evaluation을 framework-independent Python service로 구현한다.
2. FastAPI route는 얇게 그 service를 호출한다.
3. unit test는 HTTP 없이 service를 직접 호출한다.
4. Streamlit은 실제 사용자 흐름 검증 때 localhost FastAPI를 호출한다.

이렇게 하면 FastAPI를 제거해도 핵심 RAG가 동작하고, 반대로 웹앱으로 확장할 때 핵심 로직을 다시 작성하지 않는다. FastAPI 사용 여부와 외부 클라우드 API 사용 여부는 독립적인 결정이다.

### A.6 갱신된 최종 권고

외부 클라우드 API 없이 FastAPI와 전용 Vector DB를 반드시 사용한다면 다음으로 확정한다.

- `Streamlit -> FastAPI(127.0.0.1) -> PostgreSQL + pgvector / local embedder / Ollama`
- 생성: Qwen3 1.7B Q4 non-thinking, 미달 시 사내 GPU 서버의 로컬 7B~8B로 adapter만 교체
- embedding: multilingual-e5-small, 동일 평가에서만 BGE-M3 challenger 비교
- pgvector: exact cosine부터 시작; approved/effective/access predicates를 SQL에 강제
- 인터넷: 실행 중 egress deny, model artifact checksum 사전 반입, cloud client dependency/config 금지
- 사내망 공개 전: TLS proxy, Google Workspace OIDC/Group 권한, 명시적 origin/host, 최소 DB 권한, redacted logs

Chroma는 PostgreSQL 준비가 불가능한 짧은 로컬 검색 실험의 대체안으로만 둔다. 이 판단은 Chroma의 검색 품질이 낮아서가 아니라, 공식 문서가 PersistentClient를 개발/테스트용으로 분류하고 현재 self-hosted server의 인증 경계를 별도로 요구하며, 이 프로젝트가 이미 관계형 승인·로그·세션과 운영 PostgreSQL을 필요로 하기 때문이다.

### 부록 공식 출처

- Chroma: [Python clients](https://docs.trychroma.com/reference/python), [client-server mode](https://docs.trychroma.com/docs/run-chroma/client-server), [server configuration](https://docs.trychroma.com/reference/server-env-vars), [migration/auth changes](https://docs.trychroma.com/updates/migration)
- pgvector: [official repository and Windows/Docker installation](https://github.com/pgvector/pgvector), [querying](https://github.com/pgvector/pgvector#querying), [filtering](https://github.com/pgvector/pgvector#filtering)
- FastAPI: [request bodies](https://fastapi.tiangolo.com/tutorial/body/), [CORS](https://fastapi.tiangolo.com/tutorial/cors/), [HTTPS](https://fastapi.tiangolo.com/deployment/https/), [advanced middleware](https://fastapi.tiangolo.com/advanced/middleware/)
- Local runtime: [Ollama Windows](https://github.com/ollama/ollama/blob/main/docs/windows.mdx), [Ollama local API](https://docs.ollama.com/api/introduction)

## 부록 B. 개발로드맵 B: 컴포넌트 간 API 연결 없는 embedded RAG

### B.1 정의와 현실성

개발로드맵 B는 외부 클라우드 API와 localhost 내부 API를 호출하지 않는다. 앱 runtime은 한 Python 프로세스 안에서 다음 객체를 직접 호출한다. 단, Streamlit 자체는 브라우저 UI를 위해 localhost HTTP/WebSocket 서버를 사용하므로 네트워크 공격면이 0인 구조는 아니다. 비신뢰 문서 파싱만 시간·메모리 제한을 강제할 수 있는 저권한 disposable subprocess로 격리하며 API나 port를 열지 않는다.

`Streamlit(or CLI) -> isolated parser worker / local embedder -> embedded Vector DB -> local generator`

- Streamlit은 Python service 함수를 직접 호출한다.
- embedding 모델은 `sentence-transformers` 등으로 메모리에 적재하고 query/document vector를 프로세스 안에서 계산한다.
- Vector DB는 로컬 경로를 여는 embedded client를 사용한다. 별도 database server나 port는 없다.
- 생성은 로컬 GGUF를 `llama-cpp-python`의 `Llama` 객체로 직접 호출하거나, 로컬 파일만 읽는 Transformers pipeline으로 수행한다.
- PDF/DOCX parser, 원문, 모델, tokenizer, GGUF, DB 파일을 사전에 반입한다. 실행 중 다운로드와 원격 model ID 조회는 금지한다.

이 구성은 기술적으로 가능하며 현재의 단일 HR 평가자·소규모 문서·100문항 품질 검증에는 적합하다. 앱 runtime의 native inference crash/OOM, Streamlit rerun, 모델 교체는 UI·검색·생성을 함께 중단시킨다. parser subprocess 장애는 candidate 구축 실패로 격리한다. 인증·권한·rate limit을 중앙 강제하는 API 경계도 없으므로 사내 다중 사용자 운영 구조로 보지 않는다.

### B.2 embedded Vector DB 비교

| 후보 | 공식적으로 확인된 로컬 동작 | Windows/Python 3.12 현실성 | 현재 범위의 판단 |
|---|---|---|---|
| **LanceDB OSS** | 공식 quickstart가 SQLite처럼 앱 프로세스 안에서 실행되는 embedded DB로 정의하고 로컬 path 연결을 제공한다. vector, full-text, hybrid, metadata filter와 table versioning을 제공한다. | PyPI의 CPython 3.9+ Windows x86-64 `abi3` wheel이 Python 3.12를 포함한다. Apache-2.0. | **B의 1순위.** 별도 metadata DB 없이 출처·시행일·등급·index version을 함께 관리하고, 한국어 dense+keyword challenger를 같은 저장소에서 시험하기 쉽다. |
| Chroma `PersistentClient` | 로컬 directory에 저장하는 embedded client다. 별도 server/HTTP가 필요 없다. | PyPI가 Python 3.9+와 Windows x86-64 wheel을 제공한다. Apache-2.0. | 가장 단순한 runner-up. 다만 공식 문서는 `PersistentClient`를 local development/testing 용도로 안내한다. 폐기형 검색 실험에는 충분하지만 B의 버전 비교·승인/rollback workflow에는 LanceDB가 더 직접적이다. |
| FAISS CPU | Python 프로세스 안에서 exact/approximate vector index를 실행하고 index file을 저장할 수 있다. MIT. | 공식 지원 설치 경로는 Conda이며 Windows x86-64 CPU package가 있다. GPU package는 Linux만 지원한다. 공식 문서는 PyPI install을 지원 경로로 제시하지 않는다. | 검색 엔진으로는 견고하지만 문서·metadata·승인 버전은 별도 SQLite/파일로 구현해야 한다. Python 3.12 venv 중심 설치와 운영 코드가 늘어나므로 이번 B에서는 제외한다. |

현재 규모는 PDF 10개, DOCX 5개, FAQ 약 200건이므로 처음부터 ANN index를 만드는 이점이 작다. LanceDB 공식 문서도 수십만 vector 이하에서는 brute-force kNN이 충분한 경우가 많다고 설명한다. 따라서 **LanceDB local table + exact dense search**로 시작하고, 한국어 동의어·규정 번호 검색에서 실패할 때만 FTS와 RRF hybrid를 활성화한다. 이것은 불필요한 index tuning을 피하면서 평가 결과로 복잡도를 정하는 선택이다.

청크 row에는 최소한 `chunk_id`, `document_id`, `title`, `page_or_section`, `text`, `source_uri`, `effective_from`, `effective_to`, `access_level`, `content_hash`, `index_version`, `embedding_model_id`, `vector`를 둔다. LanceDB table version/tag는 실험 재현과 rollback 보조 수단으로 사용하되, HR의 승인 상태와 문서 효력 규칙 자체는 명시적 column과 검증 코드로 유지한다.

### B.3 in-process 생성 선택

#### 권장: `llama-cpp-python` + 로컬 GGUF

공식 저장소는 `llama-cpp-python`을 llama.cpp Python binding으로 설명하며, 선택적 web server를 거치지 않고 `Llama(model_path=...)`와 `create_chat_completion()`을 직접 호출하는 high-level API를 제공한다. 라이선스는 MIT다. 이 프로젝트에서는 승인된 로컬 GGUF의 절대 경로만 사용하고 `from_pretrained()` 같은 다운로드 경로를 사용하지 않는다.

1순위 실험은 앞서 선정한 **Qwen3 1.7B Q4, non-thinking**이다. 모델 카드의 Apache-2.0 조건과 GGUF 배포자의 provenance/checksum을 함께 기록한다. 8GB RAM/4GB VRAM PC에서는 context 2K~4K, 동시 생성 1, 짧은 Top-K context부터 측정한다. 모델 파일 크기만으로 메모리 적합성을 판단할 수 없다. weights 외에도 KV cache, compute buffer, Python, embedder, Streamlit, Vector DB가 같은 RAM/VRAM을 사용한다는 점에 근거한 보수적 추론이다.

설치 위험은 분명하다. 기본 `pip install`은 native llama.cpp를 빌드하므로 Windows에서는 Visual Studio 또는 MinGW toolchain이 필요하다. 공식 CPU wheel, Python 3.12용 CUDA wheel, Windows Vulkan wheel 경로가 있으나 CUDA version·GPU compute capability·wheel index가 맞아야 한다. 설치 재현성을 위해 Python, wheel URL, CUDA/driver, GGUF hash를 lock하고 CPU wheel을 항상 fallback으로 검증한다. native library crash나 OOM은 같은 Streamlit 프로세스를 종료할 수 있다.

#### 비교군: Transformers + 로컬 model directory

Transformers도 `pipeline("text-generation", model=<local path or model object>)`로 같은 프로세스에서 생성할 수 있다. 공식 설치 문서는 Python 3.10+와 PyTorch 2.4+를 안내하며, 사전 다운로드 후 `HF_HUB_OFFLINE=1`과 `local_files_only=True`로 HTTP 요청을 차단할 수 있다. `trust_remote_code=True`는 model repository code를 실행하므로 승인 없이 사용하지 않는다.

그러나 이 PC에서는 우선순위가 낮다. 1.7B fp16 parameter만 단순 계산해도 약 3.4GB이고, 실제 실행에는 activation/cache/PyTorch allocator와 다른 앱의 메모리가 추가된다. 이는 parameter 수와 dtype에 기반한 추정치이지 공식 보장값이 아니다. 4-bit 실행은 별도 quantization backend와 Windows/CUDA 호환성 위험을 더한다. 따라서 Transformers는 원본 모델 동작 비교나 더 큰 RAM/GPU 장비에서만 challenger로 두고, B의 기본 생성기는 GGUF 기반 `llama-cpp-python`으로 한다. 어느 경우든 모델 라이선스는 inference library 라이선스와 별도로 검토한다.

### B.4 lifecycle, 동시성, 보안 경계

- Streamlit의 `st.cache_resource`로 embedder, LanceDB connection, `Llama` 객체를 process-wide singleton으로 적재한다. 공식 문서가 이 cache를 ML model/database connection 같은 resource용으로 정의하며, global resource는 thread-safe해야 한다고 경고한다.
- 생성 호출은 우선 lock/queue로 1개만 허용한다. 여러 브라우저 session이 동시에 같은 native context를 호출하지 않게 하고, 응답시간 중앙값과 queue wait를 분리 계측한다.
- parsing/indexing과 chat을 동시에 실행하지 않는다. candidate table을 완성·평가한 뒤 active index pointer를 원자적으로 교체한다.
- browser에는 파일 경로, 원문 corpus, model path를 노출하지 않는다. Streamlit upload를 허용한다면 크기·확장자·MIME·압축 해제량·저장 경로를 검증하고 HR 관리자 session에만 제한한다.
- 별도 API·DB port가 없어 공격면은 줄지만 Streamlit localhost port는 남는다. 로컬 파일 권한과 Python dependency/native wheel 공급망도 핵심 경계이므로 모델·wheel·문서 checksum, 승인 manifest, Windows ACL, egress deny를 적용한다.
- embedded app에는 SSO/API authorization 경계가 없다. Streamlit을 LAN에 직접 공개하는 방식으로 운영 단계에 승격하지 않는다.

### B.5 생성 모델을 제외하면 RAG가 아니다

원 RAG 논문은 parametric sequence-to-sequence generator와 non-parametric dense retriever/index를 결합해 언어를 생성하는 구조로 RAG를 정의한다. 따라서 embedding과 Vector DB로 승인 FAQ/청크만 찾아 그대로 표시하고 **생성 모델을 전혀 사용하지 않으면 retrieval-only FAQ/search**다.

retrieval-only는 잘못이 아니라 이 HR prototype의 강한 baseline이다. 승인된 FAQ 답변·원문 구절·출처만 반환하므로 환각 위험과 latency가 낮다. 반면 여러 청크를 종합하거나 사용자 표현에 맞춰 설명하지 않는다. UI와 평가표에서는 다음을 혼동하지 않는다.

- `검색형 FAQ`: Top 1 승인 답변 또는 Top K 원문/출처를 그대로 표시
- `RAG`: 검색된 근거를 generator가 종합하되 citation allowlist와 근거 부족 거절을 적용

먼저 검색형 FAQ로 Recall@5, 유효 출처, 근거 없는 질문 거부를 측정하고, 같은 질문 세트에서 generator가 실제로 답변 정확도를 높이는지를 추가 측정한다. generator가 85% 정확도 또는 5초 중앙값을 악화시키면 검색형 FAQ를 사용자 응답 기본값으로 유지할 수 있다.

### B.6 개발로드맵 A/B 비교와 권고

| 판단축 | 개발로드맵 A: 내부 API 분리 | 개발로드맵 B: embedded app runtime + 격리 parser worker |
|---|---|---|
| 구성 | Streamlit/Next.js → FastAPI → pgvector/local Ollama | Streamlit/CLI → Python 함수 → LanceDB/local embedder/`llama-cpp-python`; parser만 격리 worker |
| HTTP/port | loopback 또는 사내망 내부 API 존재 | 컴포넌트 간 API 호출은 없지만 Streamlit localhost port는 존재 |
| 초기 설치·디버깅 | 여러 process/service와 contract 필요 | 가장 단순; 한 debugger에서 전체 pipeline 확인 |
| 오프라인성 | 완전 로컬 가능하지만 내부 HTTP 사용 | artifact 사전 반입 시 network call 0으로 검증 가능 |
| 장애 격리 | UI/API/model/DB를 분리·재시작 가능 | generator crash/OOM/rerun은 앱 전체에 영향; parser crash는 candidate 실패로 격리 |
| 인증·권한 | API/proxy에서 SSO, role, rate limit 중앙 강제 | OS 사용자·로컬 파일 경계 중심; 다중 사용자 운영에 부적합 |
| 평가 재현 | API contract와 pgvector snapshot 필요 | Python environment와 local table/model manifest로 단순 재현 |
| 확장 | Next.js, Google Workspace SSO, 다중 사용자, 독립 scaling에 적합 | 단일 평가자·단일 PC 품질 prototype에 적합 |
| 전환 비용 | 운영 기반을 일찍 구축 | service interface를 지키면 core logic을 FastAPI adapter 뒤로 이동 가능 |

**권고는 1차 정확도 prototype에 B, 파일럿·운영 전환에 A다.** 둘은 상호 배타적인 제품안이 아니라 단계별 배치안이다.

1. B에서 parser, chunk schema, embedding, retrieval, generation, citation validator, evaluator를 framework-independent Python service 함수로 만든다.
2. LanceDB exact dense와 retrieval-only baseline을 먼저 통과시킨 뒤 hybrid와 generator의 증분 효과만 비교한다. Streamlit은 `127.0.0.1`에만 bind하고 XSRF 보호와 Windows Firewall inbound 차단을 유지한다.
3. 답변 가능 질문에서 retrieval 63/70 이상과 HR 생성 판정 60/70 이상, 거절 질문 29/30 이상, 유효 출처 100%, 중대 오류 0건을 통과시킨다. 성능은 답변 가능 70개 생성 경로의 중앙값 5초 이하로 판정한다.
4. Google Workspace SSO, 다중 사용자, 관리자 업로드/승인, Next.js 또는 중앙 로그가 필요해지는 시점에 A로 전환한다. service 함수 앞에 얇은 FastAPI route를 붙이고 저장 adapter를 PostgreSQL+pgvector로 교체한다.

B를 폐기형 코드로 만들지 않기 위한 공개 seam은 구현이 실제로 교체되는 `VectorStore`와 `Generator` interface 및 순수 domain record다. parser와 embedder는 KnowledgeModule 내부 구현으로 유지하고, 평가 흐름은 EvaluationModule의 작은 interface로 제공한다. 분산 orchestration, background queue, 별도 repository layer는 B에서 만들지 않는다.

### 부록 B 공식 출처

- LanceDB: [embedded quickstart](https://docs.lancedb.com/quickstart), [PyPI Windows/Python wheel metadata](https://pypi.org/project/lancedb/), [search and hybrid search](https://docs.lancedb.com/search), [table versioning](https://docs.lancedb.com/tables/versioning), [table/index sizing](https://docs.lancedb.com/tables), [local embedding](https://docs.lancedb.com/embedding/quickstart), [official repository and license](https://github.com/lancedb/lancedb)
- Chroma: [Python `PersistentClient`](https://docs.trychroma.com/reference/python), [PyPI Windows/Python metadata](https://pypi.org/project/chromadb/)
- FAISS: [official installation matrix](https://github.com/facebookresearch/faiss/blob/main/INSTALL.md), [MIT license](https://github.com/facebookresearch/faiss/blob/main/LICENSE)
- llama-cpp-python: [official repository, direct `Llama` API and installation](https://github.com/abetlen/llama-cpp-python), [MIT license](https://github.com/abetlen/llama-cpp-python/blob/main/LICENSE.md)
- Transformers: [installation and offline mode](https://huggingface.co/docs/transformers/installation), [text-generation pipeline](https://huggingface.co/docs/transformers/main/en/main_classes/pipelines)
- Streamlit: [`st.cache_resource`](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_resource)
- RAG definition: [Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401)
