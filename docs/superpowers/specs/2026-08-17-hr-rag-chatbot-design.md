# HR RAG 챗봇 설계

- 작성일: 2026-08-17 KST
- 상태: 설계 섹션 1~5 사용자 승인 완료
- 대상: HR 평가 담당자용 로컬 프로토타입에서 사내 임직원용 운영 웹앱으로 전환
- 관련 문서: [도메인 용어](../../../CONTEXT.md), [기술 조사](../../research/2026-08-17-local-rag-prototype-options.md), [디자인 시스템](../../../DESIGN.md)

## 1. 목적

사내 임직원이 복리후생, 휴가 제도, 사내 규칙과 HR 서식을 승인된 원문에 근거해 안내받는 챗봇을 만든다. 먼저 단일 HR 평가자가 컴포넌트 간 API 연결 없이 정확도를 검증하고, 모든 품질·보안 게이트를 통과한 뒤 내부 API와 SSO를 갖춘 다중 사용자 구조로 전환한다.

## 2. 범위

### 포함

- 한국어 HR FAQ와 서식 링크·작성 방법 안내
- 원본 텍스트 PDF 10개와 DOCX 5개를 앱 밖 오프라인 절차에서 변환·검수한 TXT/MD snapshot, 승인된 웹 FAQ CSV/JSON 약 200건
- 승인 snapshot 본문 파싱; 원본 문서명·페이지·조항·원본 링크 metadata 인용
- 최근 5턴의 세션 내 대화 문맥
- 채팅 검증, 문서 현황, 평가 결과의 Streamlit 3탭
- 후보 지식 인덱스 평가, 승인, 이전 승인본 rollback
- 도움 됨/안 됨과 선택적 의견
- 로드맵 B에서 A로의 단계적 전환

### 제외

- 개인 잔여 휴가, 급여, 평가, 징계 등 개인 데이터 조회
- 휴가 신청, 서식 자동 작성, 전자결재 제출
- 스캔 PDF OCR과 이미지 설명
- HR 전용·제한 문서 검색
- 다국어 답변
- 자동 하이퍼파라미터 튜닝
- 문서 본문을 편집하는 CMS
- LangChain과 선제적 background queue

## 3. 성공 기준

고정 평가 세트는 답변 가능 질문 70개와 안전 거절 대상 30개로 구성한다. HR 평가자 1명이 정답과 근거를 확정하고 생성 답변을 최종 판정한다.

- Retrieval hit@5: 답변 가능 질문 중 63/70 이상
- 생성 답변 정확도: 답변 가능 질문 중 60/70 이상
- 근거 없는 질문 안전 거절률: 거절 대상 질문 중 29/30 이상
- 유효한 정책 답변의 출처 표시: 100%
- 중대 오류: 0건
- 워밍업 후 답변 가능 70개가 생성 경로에서 질문 제출부터 완성된 `AnswerResult` 반환까지 걸린 시간의 중앙값: 5초 이하
- 100문항 전체 실행 중 OOM: 0건

중대 오류는 존재하지 않는 규정·수치 생성, 잘못된 근거 인용, 개인 데이터를 조회한 것처럼 답변, 근거 없는 확정 답변이다. 하나라도 발생하면 평균 점수와 관계없이 실패한다.

1차 자동 평가는 retrieval hit@5와 답변·정답 embedding 유사도를 계산해 HR 검토 대상을 정렬한다. 유사도는 보조 지표이며 최종 정오 판정에 사용하지 않는다. 2차 HR 평가는 정답성·근거성·안전성을 각각 통과/실패로 판정하며, 셋 중 하나라도 미입력 또는 실패면 해당 질문은 실패다. 비율은 정수 통과 건수를 기준으로 판정하고 화면에는 소수점 한 자리로 표시한다.

다음 보안 조건도 완료 게이트다.

- 고정 adversarial 평가 세트에서 prompt-injection 정책 우회 0건
- 중요 수치·날짜·기간·비율과 인용 근거 일치 100%
- candidate 또는 부분 색인의 일반 질문 노출 0건
- 평가 manifest와 승인 manifest 불일치 시 승인 성공 0건
- 실행 중 허용되지 않은 외부 egress 0건
- 대화·피드백 보존 데이터의 30일 삭제 검증 성공

## 4. 개발로드맵

### 로드맵 B: 컴포넌트 간 API 연결 없는 정확도 프로토타입

```text
Streamlit
  -> Python module interface
  -> parser / chunker / local embedder
  -> LanceDB embedded
  -> llama-cpp-python + local GGUF
  -> citation validator
```

외부 클라우드 API, localhost 내부 API, 별도 DB·모델 서버를 사용하지 않는다. 단, Streamlit은 브라우저 UI를 위해 localhost HTTP/WebSocket 서버를 사용한다. `127.0.0.1`에만 bind하고 XSRF 보호와 Windows Firewall inbound 차단을 유지한다.

기본 생성 후보는 Qwen3 1.7B Q4 non-thinking, 기본 임베딩 후보는 `multilingual-e5-small`이다. 모델·tokenizer·native wheel은 승인된 artifact를 사전 반입하고 실행 중 다운로드를 금지한다.

### 로드맵 A: 내부 API 분리형 운영 구조

```text
Streamlit or Next.js
  -> TLS proxy / Google Workspace SSO
  -> FastAPI
  -> PostgreSQL + pgvector
  -> Ollama or internal model server
```

로드맵 B의 핵심 모듈 인터페이스와 도메인 record를 유지한다. FastAPI는 얇은 adapter로 추가하고, LanceDB와 llama-cpp adapter를 pgvector와 Ollama adapter로 교체한다.

### 전환 조건

로드맵 B의 파싱·검색·승인·보안 게이트를 모두 통과하고 로컬 1.7B 생성기만 품질 또는 5초 기준에 미달하면, 임직원에게 노출하지 않는 **B.5 생성기 상향 진단**에서 같은 retrieval context를 사내 7B~8B 생성기로 비교할 수 있다. 이 단계는 내부 모델 호출 adapter만 시험하며 운영용 A 전환으로 간주하지 않는다. B.5는 **진단 전용**이며, 결과는 candidate를 승인하거나 B 완료 게이트를 충족하지 않는다. A 평가 환경에서 사용할 generator와 hardware를 선택하는 자료로만 사용한다.

로드맵 A의 제한된 평가 환경은 B의 파싱·검색·승인·보안 게이트를 통과하고, SSO·다중 사용자 같은 운영 필요가 생기거나 B.5가 목표 generator·hardware를 선택한 뒤에만 구축한다. 전환 뒤 LanceDB와 pgvector의 chunk ID·내용 해시·개수·filter 의미가 일치해야 하며 전체 100문항을 다시 실행한다. 전체 품질 게이트까지 목표 장비에서 통과한 뒤에만 임직원 파일럿을 시작할 수 있다. 파싱·승인·보안 게이트 미달은 B.5 또는 A 전환 사유가 아니며 먼저 B에서 수정한다.

## 5. 도메인 데이터

### DocumentVersion

- `document_id`, `version_id`
- 제목과 승인된 `source_uri`
- 시행일과 만료일
- 문서 우선순위
- 원본 `content_hash`

문서 내용이 바뀌면 기존 record를 덮어쓰지 않고 새 버전을 만든다.

### KnowledgeChunk

- 안정적인 `chunk_id`와 `version_id`
- 페이지, 조항, 표 위치
- 원문 text와 embedding vector
- 임직원 공개 등급
- 문서·인덱스 내용 해시

표는 제목·열 머리글·행 머리글을 보존한 검색용 text와 사람이 확인할 Markdown을 함께 가진다.

### KnowledgeIndex

- `index_id`
- `candidate`, `approved`, `retired` 상태
- embedding 모델과 revision
- 청킹·검색 설정
- 생성 시각과 승인 시각
- 불변 manifest hash

최초 승인 전에는 활성 `approved` 인덱스가 0개일 수 있고, 최초 승인 뒤에는 정확히 하나만 허용한다.

### EvaluationRun

- `evaluation_id`, `index_id`
- 평가 세트 checksum
- 모델·인덱스·설정 식별자
- retrieval, generation, refusal, safety, timing 결과
- 질문별 결과와 실패 원인

### EvaluationCase와 HumanReview

`EvaluationCase`는 `case_id`, 질문, `answerable/refusal` 기대 유형, 안정적인 `document_version_id`, 페이지·조항, anchor text와 anchor hash, 기준 답변, 중요 사실 목록과 category를 가진다. 특정 chunk ID는 정답 라벨로 사용하지 않는다. 평가 실행 시 현재 candidate chunk가 anchor 범위를 포함하는지 매핑하고, 실제 검색된 chunk ID는 실행 결과에만 기록한다. `HumanReview`는 `case_id`, 정답성·근거성·안전성 판정, 의견, 평가자와 KST 판정 시각을 가진다.

### Feedback

로드맵 B는 단일 HR 평가자이므로 사용자 ID를 저장하지 않는다. `Feedback`은 `feedback_id`, 질문·답변 snapshot, citation ID, 도움 됨/안 됨, 선택 의견, 생성·만료 시각을 가지며 30일 뒤 원문을 삭제하고 비식별 집계만 남긴다. 로드맵 A에서 사용자 연계가 필요하면 회사 관리 secret으로 HMAC한 event-level 가명 ID를 사용하고 원본 이메일을 저장하지 않는다. 가명 ID도 30일 뒤 event와 함께 삭제하며 장기 집계에는 어떤 사용자 식별자도 남기지 않는다.

모든 일시는 KST의 `yyyy-MM-dd HH:mm:ss KST` 형식으로 기록한다.

## 6. 지식 수명주기

```text
data/inbox
  -> 형식·metadata·hash 검증
  -> 파싱·표 정규화·청킹·임베딩
  -> candidate 생성 및 봉인
  -> 고정 100문항 평가
  -> HR 평가자 승인
  -> active approved pointer 원자적 전환
  -> 이전 approved를 retired로 보존
```

- 앱 입력은 HR이 checksum으로 승인한 UTF-8 TXT, MD, CSV, JSON snapshot만 허용한다. PDF, DOCX와 HTML은 앱 밖 오프라인 절차에서 변환·검수하며 runtime ingestion에서 즉시 거절한다.
- `metadata.csv`는 제목, 원본 URI, 우선순위, 시행일, 만료일과 공개 등급을 관리한다.
- candidate는 평가 시작 후 immutable이다.
- 승인 시 manifest, 문서, 모델·청킹 설정 hash와 `evaluation_run_id`를 함께 검증한다.
- 부분 구축 결과나 candidate는 일반 질문에서 검색할 수 없다.
- rollback 전 문서 효력, 취소 상태, 공개 등급과 manifest hash를 다시 검사한다.
- 보안상 취소된 인덱스는 rollback할 수 없다.

로드맵 B 앱은 UTF-8 TXT/MD를 렌더링·실행하지 않는 일반 텍스트로 읽고, `question,answer` exact FAQ schema의 CSV/JSON만 stdlib로 직접 읽는다. MD의 HTML, 링크, 이미지, include 표기는 실행하거나 외부에서 가져오지 않고 원문 문자열로만 취급한다. source bytes를 한 번만 읽고 동일 bytes로 크기, 승인 checksum, encoding, NUL byte와 schema를 fail-closed로 검증하며 CLI도 inbox와 checksum을 필수로 받는다. `policy_subject`는 FAQ 본문에 넣지 않고 parser 논리 위치에 대응하는 승인 sidecar에서 결합한다. raw PDF/DOCX/HTML parser와 parser 전용 OS 계정은 제품 경로에 두지 않는다. Windows DNS Client가 사용자별 Firewall 규칙을 우회한 실측 결과 때문에 rich-document 자동 파싱은 zero-network AppContainer가 도입되는 후속 단계까지 금지한다.

로드맵 B는 process lock 아래 동일 volume의 임시 active-pointer 파일을 쓰고 flush한 뒤 atomic replace한다. replace 전에 중단되면 기존 approved가 유지된다. 승인과 rollback은 `expected_current_index_id`와 `expected_manifest_hash`를 비교하는 compare-and-swap(CAS)으로 동시 변경을 거절한다. 로드맵 A는 database transaction, row lock과 “활성 인덱스 최대 하나” 제약으로 같은 계약을 보장한다.

## 7. 답변 흐름

로드맵 B는 먼저 **retrieval-only 기준선**을 실행한다. 승인 FAQ의 일치 답변 또는 Top K 원문·출처를 생성 없이 표시해 검색 정확도와 지연을 측정한다. 이후 같은 검색 근거에 generator를 추가해 증분 효과를 비교한다. generator가 정확도 또는 5초 기준을 악화시키면 프로토타입 기본 응답은 retrieval-only로 유지하며, 생성형 답변을 임직원에게 공개하지 않는다.

```text
질문 검증·민감 패턴 마스킹
  -> approved·시행 중·임직원 공개 조건으로 Top 5 검색
  -> 근거 충분성 판정
  -> 검증 후보 답변과 citation ID 생성
  -> 중요 사실과 citation 대조
  -> 근거 기반 답변 또는 안전 거절
```

- 최근 5턴은 후속 질문을 독립 질문으로 재구성할 때만 사용한다.
- 이전 모델 답변은 정책 근거로 사용하지 않는다.
- 검색 청크는 명확한 비신뢰 데이터 영역으로 delimit한다.
- 문서 내부 지시는 시스템 규칙, 출력 형식과 거절 정책을 바꿀 수 없다.
- 모델에는 파일, DB, 네트워크 또는 도구 접근을 제공하지 않는다.
- 구조화 출력의 알 수 없는 필드는 거절한다.
- 모든 정책 주장에 citation을 요구한다.
- 자동 검사는 citation allowlist와 정규화된 날짜·금액·일수·비율의 exact match를 담당한다.
- 조건 누락과 의미적 정답성은 HR 평가자가 rubric으로 판정한다.
- 인용의 문서명·위치·URL은 모델 출력 대신 신뢰 저장소에서 재구성한다.
- `source_uri`는 `ALLOWED_SOURCE_HOSTS`에 등록된 HTTPS host만 클릭 가능한 링크로 표시한다. 로드맵 B의 로컬 TXT/MD snapshot은 본문 안의 Markdown 링크를 활성화하지 않고 원본 문서명·페이지·조항 metadata와 inbox 내 논리 위치를 표시한다.
- 근거가 부족하거나 검증이 실패하면 생성 답변을 폐기한다.

모델 장애 시 유효한 검색 원문과 출처만 “답변 생성 불가” 상태로 표시한다. 유효한 원문도 없으면 안전 거절하고 공식 문의 경로를 안내한다.

공유메일이 설정되지 않은 기본 공식 문의 문구는 “개인별 확인이 필요한 질문입니다. 회사가 지정한 HR 공식 문의 채널을 이용해 주세요.”다.

## 8. 모듈과 seam

### AnsweringModule

`answer(request) -> AnswerResult`

질문 검증, 대화 재구성, 검색, 충분성 판정, 생성, citation 검사, 안전 거절과 단계별 시간을 숨긴다.

`AnswerRequest`는 `request_id`, 최대 2,000자의 질문, 최대 5턴의 대화 문맥과 선택적 approved `index_id`를 가진다. 문자열 길이 외에 실제 모델 tokenizer로 전체 token budget을 다시 검사한다. `AnswerResult.status`는 `answered`, `refused`, `retrieval_only`, `degraded`, `error` 중 하나다. 결과는 answer text, 최대 5개의 ranked evidence, 검증된 citations, refusal reason, error code, 단계별 timings와 model/index/config ID를 가진다. 오류 code는 `invalid_input`, `no_evidence`, `storage_unavailable`, `model_unavailable`, `model_timeout`, `validation_failed`로 고정한다.

### KnowledgeModule

`build_candidate(source_snapshot, config) -> CandidateRef`

`approve(index_id, evaluation_run_id, expected_manifest_hash, expected_current_index_id, actor) -> IndexTransitionResult`

`rollback(target_index_id, expected_manifest_hash, expected_current_index_id, actor) -> IndexTransitionResult`

파싱, 표 정규화, 청킹, 임베딩, candidate 봉인과 활성 인덱스 전환을 숨긴다.

### EvaluationModule

`run(index_id, dataset) -> EvaluationReport`

`record_review(evaluation_id, case_id, correctness, grounding, safety, comment, actor) -> HumanReview`

`finalize(evaluation_id, actor) -> FinalizedEvaluationReport`

100문항 실행, 지표 계산, HR 판정과 중대 오류 게이트, 재현 정보를 숨긴다. 평가 상태는 `running -> awaiting_review -> finalized`로만 전이한다. 100개 case 모두에 완전한 HumanReview가 있어야 finalize할 수 있고, finalized 평가만 `KnowledgeModule.approve()`에 전달할 수 있다.

### 실제 adapter seam

| Seam | 로드맵 B | 로드맵 A | 테스트 |
|---|---|---|---|
| VectorStore | LanceDB | PostgreSQL+pgvector | in-memory adapter |
| Generator | llama-cpp-python | Ollama adapter | deterministic adapter |
| 호출 진입점 | Streamlit 직접 호출 | FastAPI adapter | 모듈 직접 호출 |

`VectorStore.search(query_vector, filters, k) -> list[RankedChunk]`는 score 내림차순, 동점이면 `chunk_id` 오름차순으로 정렬한다. filter에는 approved index, 시행·만료일과 공개 등급이 반드시 포함된다. `Generator.generate(question, evidence, history) -> DraftAnswer`는 answer와 주장별 citation chunk ID만 반환하며 알 수 없는 출력 필드는 실패다.

구현 하나뿐인 repository 계층, parser별 공개 인터페이스와 service/controller pass-through 계층은 만들지 않는다.

초기 참고 구조는 다음과 같다.

```text
src/hr_chatbot/
  app.py
  domain.py
  answering.py
  knowledge.py
  evaluation.py
  adapters/
    lancedb_store.py
    llama_cpp_generator.py
    document_parser.py
```

로드맵 A에서는 `api.py`, `auth.py`, `adapters/pgvector_store.py`, `adapters/ollama_generator.py`만 추가하고 세 핵심 모듈을 유지한다.

## 9. UI와 상태

[DESIGN.md](../../../DESIGN.md)의 토큰을 적용한다. Clean Light를 기본으로 Dark Theme을 지원하고 Electric Royal Blue/Indigo, 18px card, pill control과 정의된 spacing을 사용한다.

### 채팅 검증 탭

- 질문·답변, 출처와 검색 Top 5
- 검색·생성·검증 시간
- 도움 됨/안 됨과 선택적 의견
- 생성 중 중복 제출 차단

### 문서 현황 탭

- approved와 candidate 상태
- 문서별 metadata·파싱·청킹·색인 오류
- 추출 미리보기
- 평가 게이트 통과 후 승인
- 확인 후 rollback

### 평가 결과 탭

- 평가 CSV 실행
- retrieval, generation, refusal, safety, timing KPI
- 질문별 실패 원인
- 질문별 정답성·근거성·안전성 판정과 의견 입력
- 미판정 수 표시와 100건 판정 완료 후 최종 확정
- 이전 실행 비교와 결과 CSV 내보내기

빈 상태, 진행 상태, 복구 가능한 오류와 안전 차단을 명확히 구분한다. 모바일에서는 각 탭을 단일 열로 배치한다. 키보드 조작과 명시적 label을 제공하고 상태를 색상만으로 표현하지 않는다. 정렬 가능한 표는 비활성 열에 `⇅`, 활성 열에 `▲` 또는 `▼`를 표시한다.

## 10. 테스트 전략

### Snapshot parser 골든 테스트

TXT/MD 문단 경계와 CSV/JSON FAQ를 검증한다. MD는 Markdown·HTML을 렌더링하거나 링크·이미지·include를 가져오지 않는다. PDF/DOCX/HTML, 비 UTF-8, NUL byte, unknown field, 경로 탈출, symlink/reparse point와 예약 장치명을 거절한다. 원본 페이지·조항은 오프라인 변환 시 승인 metadata로 보존한다.

### 모듈 인터페이스 테스트

in-memory VectorStore와 deterministic Generator로 정상 답변, 근거 부족, 개인화 질문, citation 불일치, 모델 오류와 rollback을 관찰 가능한 결과로 검증한다.

### Adapter 계약 테스트

LanceDB와 pgvector의 filter, tie-break, Top K, cosine 정규화 의미를 같은 fixture로 검증한다. llama-cpp와 Ollama가 동일한 구조화 결과 계약을 만족하는지 확인한다.

### End-to-End 테스트

Streamlit AppTest로 3탭, candidate 구축, 자동 평가, HR 판정·최종 확정, 승인, rollback, 피드백과 CSV export를 검증한다. CSV export는 셀의 첫 non-space 문자가 `=`, `+`, `-`, `@`, tab 또는 carriage return이면 export copy 앞에 apostrophe를 붙여 formula 실행을 막고 내부 raw 값은 변경하지 않는다.

### 보안 부정 테스트

고정 checksum의 adversarial 세트를 사용해 prompt injection, 악성 문서, candidate 변조, 동시 승인, 중단된 색인, candidate 검색, 만료·취소 인덱스 rollback, 권한 회수와 외부 egress를 검증한다. 정책 우회·candidate 노출·허용되지 않은 egress는 각각 0건이어야 한다.

## 11. 보안과 개인정보

### 로드맵 B

- Streamlit은 `127.0.0.1`에만 bind한다.
- XSRF 보호와 Windows Firewall inbound 차단을 유지한다.
- UI 업로드는 비활성화하고 OS ACL이 적용된 `data/inbox`만 사용한다.
- 앱 전용 OS 계정을 사용한다.
- corpus, DB, 모델과 평가 결과를 OneDrive·공유 폴더·자동 cloud backup 경로에 두지 않는다.
- 모델, tokenizer, wheel과 native DLL의 provenance, license와 SHA-256을 manifest에 기록한다.
- hash-pinned 의존성을 사용하고 runtime download, 자동 update와 `trust_remote_code=True`를 금지한다.
- OS 방화벽으로 외부 egress를 default-deny하고 실제 DNS/HTTP 실패를 검증한다.

### 문서 파싱

- 기본 제한은 `MAX_DOCUMENT_BYTES=50 MiB`이며 TXT/MD/CSV/JSON만 허용한다. 변경 시 경계 테스트와 보안 승인이 필요하다.
- 확장자, UTF-8 encoding, NUL byte와 exact CSV/JSON schema를 검사하며 MD는 일반 텍스트로만 처리한다.
- PDF, DOCX, DOCM, HTML, archive와 실행 파일을 거절한다.
- 파일 크기를 제한하고 승인 snapshot checksum 불일치 시 candidate 전체를 실패시킨다.
- symlink, reparse point, `..`, 절대경로와 예약 장치명을 차단한다.

### 데이터 보존

질문·답변·피드백 원문은 30일 뒤 삭제한다. 앱이 직접 소유하는 삭제 범위는 session cache, 앱 log, 앱 temp, 평가 CSV export와 앱이 생성한 다운로드 파일의 대화·피드백 복제본이다. 삭제 job의 성공·실패를 감사하고 표본 복구 검사로 삭제를 증명한다.

승인 원문, approved·retired 지식 인덱스와 지식 backup은 30일 대화 보존 대상이 아니다. 별도의 회사 문서 보존·rollback 정책을 따른다. OS crash dump, Windows temp와 infrastructure backup은 앱이 삭제를 보장한다고 주장하지 않고 운영 runbook과 endpoint 정책으로 보존·삭제를 검증한다.

개인 Gmail은 운영 HR 문의 경로로 사용하지 않는다. 회사 관리형 HR 공유메일을 사용하거나 회사 보안·개인정보 담당자의 명시적 승인을 출시 게이트로 요구한다. 공유메일이 준비될 때까지 실제 mail link는 비활성화한다.

### 로드맵 A

- Authorization Code + PKCE를 사용하고 OIDC의 `state`, `nonce`, `iss`, `aud`, `azp`, `exp`, `iat`를 검증한다.
- 회사 Workspace domain을 서버에서 제한한다.
- HR 관리자 권한은 서버 측 Google Group membership으로 판정하고 조회 실패 시 거부한다.
- TLS proxy만 외부에 노출하고 FastAPI, Ollama와 PostgreSQL은 private bind한다.
- Host, CORS, CSRF, body size, timeout과 rate limit을 명시한다.
- `chat_read`, `ingest_write`, `approval`, `migration` DB 계정을 분리한다.
- 운영 Swagger/ReDoc를 비활성화하거나 관리자에게 제한한다.
- backup을 암호화하고 복구를 검증한다.

## 12. 성능과 재현성

콜드 스타트는 별도 기록한다. 3회 warmup을 제외한 고정 100문항을 동시 생성 1개로 순차 실행한다. 성능 게이트는 답변 가능 70개가 생성 경로에서 질문 제출부터 완성된 `AnswerResult`가 모듈 인터페이스에서 반환될 때까지이며 queue wait를 포함한다. timeout은 실패 건으로 계산한다. 전체 100개, 거절 30개와 B.5는 별도 지표로 기록해 빠른 거절이 생성 지연을 숨기지 못하게 한다. 검색, prompt 준비, 첫 token, 생성 완료와 검증 시간을 분리하고 median과 p95를 모두 기록하되 출시 게이트는 답변 가능 70개의 median 5초다. 실제 browser 표시 시간은 UI 관찰 지표로 기록하지만 출시 게이트에는 포함하지 않는다.

평가 실행마다 다음 manifest를 저장한다.

- source commit 또는 source snapshot ID
- Python, 의존성 lock과 OS·GPU·driver
- 모델 revision·digest·quantization·license
- 임베딩 revision·dimension·prefix·normalization
- parser version과 문서 SHA-256
- chunking, Top K, 검색 결합과 거절 threshold
- index version, 평가 세트 checksum과 KST 실행 시각
- 질문별 결과와 집계 지표

현재 장비는 i7-7700HQ, RAM 약 8GB, GTX 1050 Ti 4GB다. 1B~3B Q4와 4K context를 기본으로 검증하고 메모리 부족 시 명시적 2K profile로 낮춘다. 파싱·검색·승인·보안 게이트를 통과하고 품질 또는 5초 기준만 미달하면 B.5에서 동일 retrieval context로 생성기만 사내 7B~8B 모델에 교체해 원인을 분리한다.

질문 제한은 `MAX_QUESTION_CHARS=2000`, `MAX_HISTORY_TURNS=5`를 기본값으로 한다. 실제 tokenizer 기준 profile은 다음과 같다.

| Profile | model context | max input | history | evidence | output reserve |
|---|---:|---:|---:|---:|---:|
| 기본 4K | 4096 | 3584 | 512 | 2304 | 512 |
| fallback 2K | 2048 | 1792 | 256 | 1024 | 256 |

각 열은 각각 `MODEL_N_CTX`, `MAX_INPUT_TOKENS`, `MAX_HISTORY_TOKENS`, `MAX_EVIDENCE_TOKENS`, `MAX_OUTPUT_TOKENS` 설정 키로 저장한다.

system prompt와 질문은 max input에서 history와 evidence를 제외한 예산을 사용한다. 시작 시 `max_input + output_reserve <= model_n_ctx`와 하위 예산의 합을 검증한다. history는 오래된 턴부터 제거하고 evidence는 청크 경계를 보존한 채 낮은 순위부터 제외한다. 질문 자체가 남은 input 예산을 넘으면 잘라내지 않고 `invalid_input`으로 거절한다. 검증이 실패하면 모델을 적재하지 않는다.

`ALLOWED_SOURCE_HOSTS` 기본값은 비어 있어 링크가 모두 비활성화되며, 배포 전에 승인된 Google Drive/Docs와 사내 HR host만 명시적으로 추가한다.

## 13. 남은 위험

- HR 평가자 1명의 판정 편향
- 1.7B 모델의 정책 수치·예외 조건 생성 한계
- 구형 GPU driver와 native wheel 호환성
- 복잡한 표·병합 셀 파싱 오류
- 개인 Gmail을 회사 관리형 문의 경로로 교체해야 하는 운영 의존성

이 위험은 프로토타입 완료를 숨기지 않는다. 파싱·승인·보안 gate를 통과하지 못하면 B에서 수정한다. 이 gate를 통과하고 로컬 생성기 품질·성능만 미달하면 B.5에서 생성기를 상향 비교한다. 전체 gate를 통과하지 못한 시스템은 임직원에게 공개하지 않는다.
