# AGENTS.md (Codex Harness Core Instructions v260729)

Codex 에이전트 행동 수칙 및 하네스 엔지니어링 지침이다.

---

## 0. Karpathy 4원칙 (AI 코딩 기본 원칙)

1. **Think Before Coding**: 코드를 다루기 전 반드시 3단계로 사고한다:
   - **[이해]**: 요구사항과 코드 맥락 파악. 불명확하면 `[확인 필요]`로 사용자에게 질문.
   - **[가설]**: 수정 이유와 부작용 가설 수립. 모호하거나 과도한 요구는 `[Push back]`으로 조율.
   - **[계획]**: 최소 변경 계획 수립 후 실행.
2. **Simplicity First (단순성 우선)**:
   - 요청된 항목만 최소한으로 수정하며 불필요한 과잉 엔지니어링을 철저히 금지한다.
3. **Surgical Precision (외과적 정밀성)**:
   - 수정 대상 파일/줄만 정밀 타격한다. 관련 없는 파일 변경이나 포맷팅 남발을 금지한다.
4. **Goal-Driven Execution (목표 지향 실행)**:
   - 장기/복합 태스크 실행 시 아래 표 양식으로 진행 상황을 추적하며 완성 전 멈추지 않는다.
   | # | 하위 태스크 | 상태 | 검증 기준 |
   |---|---|---|---|

---

## 1. Check-up (실시간 품질 검사) 지침

Check-up은 AI가 코드를 작성한 직후(PostToolUse) 또는 커밋 전 프로젝트 아키텍처 및 요구사항 준수 여부를 자동 진단하는 검증 기술이다.

1. **내장 진단 도구 (/doctor)**:
   - 작업 시작 시 및 주요 단계 완료 후 `/doctor` 스킬을 호출하여 하네스 환경 및 코드 품질을 진단한다.
2. **Check-write / Linter 재구현 강제**:
   - 코드 저장/수정 직후 린터 검사를 수행한다. Lint/체크 오류 발생 시 **exit code 2**를 발생시켜 자동 재구현 및 수정을 강제한다.
3. **QA Validation (Acceptance Criteria 검증)**:
   - 모든 수정 완료 후 QA Validation 스킬을 통해 인수 조건을 최종 검증한다. 검증 통과 후에만 작업을 종료하고 결과를 보고한다.

---

## 2. 일반 실행 룰 (General Rules)

- **백업 및 복구**: 기존 파일 수정 시 원본이 훼손될 위험이 있으면 `.bak` 백업 후 작업한다.
- **오류 반복 금지**: 동일한 오류가 2회 이상 연속 발생하면 무한 루프를 멈추고 `[ERROR] 원인 / 가설 / 대안` 보고서를 작성하여 사용자 확인을 받는다.
- **시간대 고정**: 모든 일시 기록은 **한국 표준시 (KST, UTC+9)**를 적용한다 (`yyyy-MM-dd HH:mm:ss KST`).
- **보안 및 환경 변수**: API 키, 비밀번호 등 민감 정보 하드코딩을 금지하고 `.env` 또는 환경변수를 참조한다.

---

## 3. DESIGN.md 탐색 및 적용 수칙 (Source of Truth)

UI/디자인 관련 작업 시 `DESIGN.md` 소스 탐색 및 적용 수칙을 엄격히 준수한다:

### 1) 소스 탐색 우선순위
1. **1순위 (프로젝트 지침)**: 현재 작업 프로젝트 루트 디렉터리의 `DESIGN.md`
2. **2순위 (사용자 전역 지침)**: 사용자 전역 설정 디렉터리 (`%USERPROFILE%\.codex\DESIGN.md` 또는 `%USERPROFILE%\OneDrive\workspace\DESIGN.md`)

### 2) 적용 및 폴백 수칙
- **탐색 필수화**: 디자인/UI 관련 키워드 수신 시 `DESIGN.md` 읽기를 선행한다.
- **미존재 시 임의 생성 금지**: 프로젝트 및 전역 경로 모두 `DESIGN.md`가 없으면 임의 색상/폰트/여백 생성을 중단하고 사용자에게 기준 가이드 확정을 요청한다.
- **충돌 발생 시 확인 절차**: 사용자 요청과 `DESIGN.md` 지침이 충돌할 경우 트레이드오프를 설명하고 진행 방향 확인 후 진행한다.

---

## 4. 기술 스택별 세부 규격 (Tech Specifications)

1. **GitHub Actions**: workflow 파일에 `keep-alive` 스킬/패턴을 적용하여 60일 비활성화 셧다운을 방지한다.
2. **Devcontainer**: 사용자 요청이 없으면 `.devcontainer` 디렉터리 생성을 금지한다.
3. **줄바꿈 설정**: Git 저장소 루트에 `.gitattributes` (`* text=auto eol=lf`)를 배치한다.
4. **Streamlit UI**: Streamlit 1.30+ API 변경사항(`st.rerun()`, `st.dataframe` hide_index)을 준수한다.
5. **이메일 템플릿**: SVG 직접 삽입을 금지하고 PNG/JPG 래스터라이즈 이미지를 사용하며 XML 이스케이프를 적용한다.
6. **Codebase-Memory-MCP**: 프로젝트 구조 변경 시 MCP 메모리 서버 인덱스를 동기화한다.
7. **SMTP 통합**: 일부 수신자 거부(550/554) 발생 시 성공한 수신자 건은 정상 처리하는 부분 성공 핸들링을 구현한다.
8. **수집 및 발송 토글**: 데이터 수집/발송 파이프라인에는 `pipeline_enabled: true/false` Stop/Run 토글 변수를 배치한다.
9. **Data Table 정렬 기호**: 데이터 테이블 구현 시 정렬 가능 열에 정렬 상태 기호를 필수로 표시한다:
   - 비활성 정렬 열: 흐린 중립 기호 `⇅` (opacity 0.35, muted color)
   - 활성 정렬 열: 진한 방향 화살표 `▲` / `▼` (bold, primary color)
10. **Windows 배치 파일 (.bat)**: 스크립트 작성 시 한글 특수문자(`·`, `—`)를 배제하고 순수 ASCII 문자로만 작성하여 파싱 오류를 예방한다.

---

## 5. Changelog

- 2026-07-29: Codex Harness v260729 개정 (Karpathy 4원칙, Check-up 실시간 검증 패턴, KST 시간대, DESIGN.md 1/2순위 탐색 수칙, Data Table 정렬 기호 적용)
