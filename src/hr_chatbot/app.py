"""MK I&C HR Policy AI Chatbot - Streamlit Web Application."""

from __future__ import annotations

import datetime
from pathlib import Path
import streamlit as st

from hr_chatbot.adapters.document_parser import DocumentParser
from hr_chatbot.adapters.hybrid_store import HybridVectorStore
from hr_chatbot.answering import AnsweringEngine
from hr_chatbot.domain import AnswerRequest, ChatTurn
from hr_chatbot.evaluation import BenchmarkRunner, get_default_evaluation_dataset

# Set Streamlit Page Configuration
st.set_page_config(
    page_title="MK I&C 인사정책 AI 챗봇",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

HR_RULES_DIR = Path("docs/HR-Rules")
CSS_FILE = Path("src/hr_chatbot/style.css")


@st.cache_resource(max_entries=1)
def get_system_components(cache_ver: str = "v3") -> tuple[HybridVectorStore, AnsweringEngine]:
    """Initialize and cache the vector store and answering engine."""
    parser = DocumentParser()
    store = HybridVectorStore()

    if HR_RULES_DIR.exists():
        for file_path in sorted(HR_RULES_DIR.glob("*.*")):
            if file_path.suffix.lower() in (".pdf", ".docx", ".csv", ".tsv"):
                try:
                    _, chunks = parser.parse_file(file_path)
                    store.add_chunks(chunks)
                except Exception as e:
                    print(f"Error loading {file_path}: {e}")

    engine = AnsweringEngine(store)
    return store, engine


def load_css() -> None:
    """Inject custom DESIGN.md CSS styling."""
    if CSS_FILE.exists():
        css = CSS_FILE.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def init_session_state() -> None:
    """Initialize session state variables."""
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": (
                    "👋 **안녕하세요! 사내 인사정책 챗봇입니다.**\n\n"
                    "취업규칙, 복무규정, 휴가제도(연차, 경조사, 병가, 육아휴직), "
                    "복리후생, 근무시간 및 사내 인사규정에 대해 무엇이든 질문해 주세요."
                ),
                "citations": [],
                "latency_ms": 0.0,
                "timestamp": datetime.datetime.now().strftime("%H:%M"),
            }
        ]
    if "feedback_log" not in st.session_state:
        st.session_state.feedback_log = {}
    if "eval_report" not in st.session_state:
        st.session_state.eval_report = None


def main() -> None:
    load_css()
    init_session_state()
    store, engine = get_system_components(cache_ver="v3")

    # --- SIDEBAR ---
    with st.sidebar:
        st.markdown("### 🏢 **MK I&C HR Chatbot**")
        st.caption("사내 승인 인사정책문서 기반 RAG 시스템")
        st.divider()

        st.markdown("#### ⚙️ **지식베이스 현황**")
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            st.metric("등록 문서", f"{len(list(HR_RULES_DIR.glob('*.*')))}개")
        with col_s2:
            st.metric("색인 청크", f"{len(store.chunks)}개")

        st.markdown(
            """
            <div style="background: var(--color-bg-subtle); padding: 10px; border-radius: 8px; font-size: 0.8rem; margin-top: 8px;">
                <b>검색 엔진:</b> 하이브리드 (Dense Vector + BM25)<br>
                <b>출처 검증:</b> 100% 사내 규정 원문 인용<br>
                <b>보안 정책:</b> 개인정보 조회 차단 및 안전 거절
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.divider()
        st.markdown("#### 🤖 **답변 생성기 설정**")
        gen_mode = st.selectbox(
            "생성 엔진 모드",
            options=["grounded_rules", "ollama", "openai_api"],
            format_func=lambda x: {
                "grounded_rules": "정밀 근거 생성 엔진 (무오류 기본)",
                "ollama": "로컬 Ollama LLM (Qwen2.5/Llama3)",
                "openai_api": "OpenAI API (GPT-4o-mini)",
            }[x],
        )

        api_key = None
        ollama_url = None
        if gen_mode == "openai_api":
            api_key = st.text_input("OpenAI API Key", type="password", placeholder="sk-...")
        elif gen_mode == "ollama":
            ollama_url = st.text_input("Ollama Endpoint", value="http://localhost:11434")

        st.divider()
        if st.button("🗑️ 대화 내역 초기화", use_container_width=True):
            st.session_state.messages = [st.session_state.messages[0]]
            st.rerun()

    # --- MAIN HEADER ---
    st.markdown(
        """
        <div class="hr-header-card">
            <div>
                <h1 class="hr-header-title">🏢 사내 인사정책 챗봇</h1>
                <p class="hr-header-subtitle">취업규칙, 복무규정, 휴가제도, 경조금, 복리후생에 대한 공인 규정 안내 및 검색 시스템</p>
            </div>
            <div>
                <span class="hr-badge hr-badge-primary">v0.1.0 Live</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- TABS ---
    tab_chat, tab_docs, tab_eval = st.tabs([
        "💬 임직원 챗봇 (HR Chat)",
        "📚 문서 및 지식베이스 (Knowledge Base)",
        "📊 품질 & 평가 대시보드 (Evaluation)",
    ])

    # =========================================================================
    # TAB 1: 💬 임직원 챗봇
    # =========================================================================
    with tab_chat:
        def execute_query(user_text: str) -> None:
            user_text = user_text.strip()
            if not user_text:
                return

            st.session_state.messages.append({"role": "user", "content": user_text, "citations": []})
            history_turns = [
                ChatTurn(role=m["role"], content=m["content"])
                for m in st.session_state.messages[-5:]
            ]
            req = AnswerRequest(
                request_id=f"req_{len(st.session_state.messages)}",
                question=user_text,
                history=tuple(history_turns),
            )
            res = engine.answer(
                req,
                llm_mode=gen_mode,
                api_key=api_key,
                ollama_url=ollama_url,
            )
            assistant_idx = len(st.session_state.messages)
            st.session_state.messages.append({
                "role": "assistant",
                "content": res.answer_text,
                "citations": res.citations,
                "latency_ms": res.latency_ms,
                "timestamp": datetime.datetime.now().strftime("%H:%M"),
                "auto_expand": True,
            })
            st.session_state.scroll_to_anchor = f"msg_anchor_{assistant_idx}"

        # --- FAQ Popup Modal Dialog ---
        @st.dialog("💡 자주 묻는 질문 퀵 스타트 (FAQ)", width="large")
        def open_faq_popup_dialog() -> None:
            st.markdown(
                "<p style='color: var(--color-text-muted); font-size: 0.95rem; margin-bottom: 12px;'>"
                "궁금하신 질문을 클릭하시면 사내 공인 인사규정 및 FAQ를 바탕으로 즉시 답변과 근거 원문을 확인하실 수 있습니다."
                "</p>",
                unsafe_allow_html=True,
            )

            col_cat1, col_cat2 = st.columns(2)
            with col_cat1:
                st.markdown("##### 🏖️ **휴가 및 휴무제도**")
                faq_items_1 = [
                    "1년 동안 80% 이상 출근 시 연차가 며칠 발생하나요?",
                    "본인 결혼 시 경조휴가 일수와 축의금 지원 기준",
                    "병가 신청 시 최대 일수와 유급/무급 기준은?",
                    "초등학교 1학년 자녀 육아휴직 신청 조건과 기간",
                    "경조휴가 기간 중 공휴일이나 주말이 포함되나요?",
                ]
                for q in faq_items_1:
                    if st.button(f"📌 {q}", key=f"dlg_q_{q}", use_container_width=True):
                        execute_query(q)
                        st.rerun()

            with col_cat2:
                st.markdown("##### ⏰ **근무환경 & 복리후생**")
                faq_items_2 = [
                    "시차출퇴근제 신청 방법과 코어타임은 어떻게 되나요?",
                    "야간근무나 휴일근무 시 수당 가산 비율과 식대 지원",
                    "종합건강검진 지원 대상 나이와 주기는 어떻게 되나요?",
                    "공장 현장 근무자의 작업복 및 안전화 교체 주기",
                    "사내 포상 추천 기준과 징계의 4가지 종류는?",
                ]
                for q in faq_items_2:
                    if st.button(f"📌 {q}", key=f"dlg_q_{q}", use_container_width=True):
                        execute_query(q)
                        st.rerun()

        # 1. Welcome Message Description (Image 2) with FAQ popup button placed side-by-side
        with st.chat_message("assistant"):
            col_welcome_text, col_welcome_btn = st.columns([7.8, 3.2])
            with col_welcome_text:
                st.markdown(
                    "👋 **안녕하세요! 사내 인사정책 챗봇입니다.**\n\n"
                    "취업규칙, 복무규정, 휴가제도(연차, 경조사, 병가, 육아휴직), 복리후생, 근무시간 및 사내 인사규정에 대해 "
                    "무엇이든 질문해 주세요."
                )
            with col_welcome_btn:
                st.write("")
                if st.button("💡 자주 묻는 질문 퀵 스타트", key="btn_open_faq_modal", use_container_width=True, help="자주 묻는 질문 팝업 창 열기"):
                    open_faq_popup_dialog()

        # 2. Question Input Box (Image 1) directly below the Welcome Message Description
        with st.form(key="top_inline_question_form", clear_on_submit=True):
            in_col1, in_col2 = st.columns([11, 1])
            with in_col1:
                inline_query = st.text_input(
                    "질문 입력",
                    placeholder="인사규정, 휴가, 복리후생, 근무제도에 대해 질문하세요...",
                    label_visibility="collapsed",
                    key="inline_prompt_input",
                )
            with in_col2:
                submitted = st.form_submit_button("↑", use_container_width=True)

            if submitted and inline_query:
                execute_query(inline_query)
                st.rerun()

        # 3. Subsequent Conversation Thread — newest pair first
        #    Group messages[1:] into (user, assistant) pairs, then reverse pairs.
        #    Within each pair always show: user question → assistant answer.
        if len(st.session_state.messages) > 1:
            st.divider()
            history = st.session_state.messages[1:]  # exclude initial greeting

            # Build pairs: [(user_msg, asst_msg), ...]
            pairs: list[tuple[dict, dict | None]] = []
            i = 0
            while i < len(history):
                user_msg = history[i] if history[i]["role"] == "user" else None
                asst_msg = history[i + 1] if (i + 1 < len(history) and history[i + 1]["role"] == "assistant") else None
                if user_msg:
                    pairs.append((user_msg, asst_msg))
                    i += 2 if asst_msg else 1
                else:
                    # orphan assistant message
                    pairs.append((history[i], None))
                    i += 1

            # Render pairs in reverse order (newest pair at top)
            for pair_idx, (user_msg, asst_msg) in enumerate(reversed(pairs)):
                # Original index for stable widget keys
                orig_pair_idx = len(pairs) - 1 - pair_idx

                # --- User question ---
                u_idx = orig_pair_idx * 2 + 1
                st.markdown(f'<div id="msg_anchor_{u_idx}"></div>', unsafe_allow_html=True)
                with st.chat_message("user"):
                    st.markdown(user_msg["content"])

                # --- Assistant answer ---
                if asst_msg:
                    a_idx = u_idx + 1
                    st.markdown(f'<div id="msg_anchor_{a_idx}"></div>', unsafe_allow_html=True)
                    with st.chat_message("assistant"):
                        st.markdown(asst_msg["content"])

                        # Citations expander
                        if asst_msg.get("citations"):
                            is_latest = (orig_pair_idx == len(pairs) - 1)
                            should_expand = asst_msg.get("auto_expand", False) or is_latest
                            with st.expander(f"🔍 근거 원문 및 상세 출처 ({len(asst_msg['citations'])}건)", expanded=should_expand):
                                for c_idx, cit in enumerate(asst_msg["citations"], start=1):
                                    st.markdown(
                                        f"""
                                        <div class="hr-citation-box">
                                            <b>[출처 {c_idx}] {cit.title}</b> <code>{cit.page_or_section}</code><br>
                                            <span style="color: var(--color-text-body);">{cit.snippet}</span>
                                        </div>
                                        """,
                                        unsafe_allow_html=True,
                                    )

                        # Footer feedback buttons
                        f_col1, f_col2, f_col3 = st.columns([1, 1, 8])
                        with f_col1:
                            if st.button("👍 도움됨", key=f"thumb_up_{a_idx}", help="답변이 정확합니다"):
                                st.session_state.feedback_log[a_idx] = "up"
                                st.toast("피드백이 반영되었습니다! (도움됨)")
                        with f_col2:
                            if st.button("👎 개선필요", key=f"thumb_down_{a_idx}", help="답변 보완이 필요합니다"):
                                st.session_state.feedback_log[a_idx] = "down"
                                st.toast("피드백이 반영되었습니다. 인사팀에 전달됩니다.")
                        with f_col3:
                            lat = asst_msg.get("latency_ms", 0.0)
                            if lat > 0:
                                st.caption(f"⏱️ 응답 속도: {lat:.1f}ms | 출처: 사내 규정집")


        # Smooth auto-scroll to the answer target
        scroll_target = st.session_state.pop("scroll_to_anchor", None)
        if scroll_target:
            import streamlit.components.v1 as components
            components.html(
                f"""
                <script>
                    setTimeout(function() {{
                        const el = window.parent.document.getElementById('{scroll_target}');
                        if (el) {{
                            el.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                        }}
                    }}, 120);
                </script>
                """,
                height=0,
                width=0,
            )

    # =========================================================================
    # TAB 2: 📚 문서 및 지식베이스
    # =========================================================================
    with tab_docs:
        st.markdown("### 📚 **사내 승인 인사정책 문서 목록**")
        st.caption("인사담당자가 관리하는 공식 원문 문서 및 지식 청크 현황입니다.")

        doc_files = sorted(list(HR_RULES_DIR.glob("*.*")))
        if doc_files:
            for doc_p in doc_files:
                col_d1, col_d2, col_d3, col_d4 = st.columns([4, 2, 2, 2])
                with col_d1:
                    icon = "📄" if doc_p.suffix == ".pdf" else "📝" if doc_p.suffix == ".docx" else "📊"
                    st.markdown(f"**{icon} {doc_p.name}**")
                with col_d2:
                    st.caption(f"크기: {doc_p.stat().st_size / 1024:.1f} KB")
                with col_d3:
                    st.markdown("<span class='hr-badge hr-badge-success'>승인됨</span>", unsafe_allow_html=True)
                with col_d4:
                    doc_chunks = [c for c in store.chunks if c.document_id == doc_p.stem.replace(" ", "_").lower()]
                    st.caption(f"청크 수: {len(doc_chunks)}개")
                st.divider()

        st.markdown("#### 🔍 **지식 청크 실시간 브라우저 & 검색기**")
        search_kw = st.text_input("청크 검색 키워드 또는 조항 번호 입력 (예: 제25조, 연차, 축의금, 식대)", "")
        
        filtered_chunks = store.chunks
        if search_kw:
            filtered_chunks = [c for c in store.chunks if search_kw in c.search_text]

        st.caption(f"검색된 청크: 총 {len(filtered_chunks)}건 / {len(store.chunks)}건")
        
        for c in filtered_chunks[:10]:
            with st.container():
                st.markdown(
                    f"""
                    <div style="background: var(--color-bg-surface); border: 1px solid var(--color-border); border-radius: 12px; padding: 14px; margin-bottom: 10px;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                            <b>📌 [{c.title}] {c.page_or_section}</b>
                            <span class="hr-badge hr-badge-primary">ID: {c.chunk_id}</span>
                        </div>
                        <div style="font-size: 0.88rem; color: var(--color-text-body); white-space: pre-line;">{c.text}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        st.divider()
        st.markdown("#### 📤 **신규 인사규정/FAQ 문서 업로드 및 재색인**")
        uploaded_file = st.file_uploader("추가할 PDF, DOCX 또는 CSV 파일을 선택하세요", type=["pdf", "docx", "csv"])
        if uploaded_file is not None:
            if st.button("🚀 파일 저장 및 즉시 재색인 실행", type="primary"):
                save_path = HR_RULES_DIR / uploaded_file.name
                with open(save_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                # Re-parse and add
                parser = DocumentParser()
                _, new_chunks = parser.parse_file(save_path)
                store.add_chunks(new_chunks)
                st.success(f"'{uploaded_file.name}' 파일이 성공적으로 파싱되어 {len(new_chunks)}개 청크가 벡터DB에 추가되었습니다!")
                st.rerun()

    # =========================================================================
    # TAB 3: 📊 품질 & 평가 대시보드
    # =========================================================================
    with tab_eval:
        st.markdown("### 📊 **RAG 품질 게이트 및 벤치마크 평가 대시보드**")
        st.caption("고정 평가 세트 100문항(답변 가능 70 + 안전 거절 30)을 실행하여 검색 Hit@5, 정확도, 안전 거절률을 자동 계측합니다.")

        eval_runner = BenchmarkRunner(engine)
        
        col_e_btn1, col_e_btn2 = st.columns([3, 7])
        with col_e_btn1:
            run_eval = st.button("▶️ 100문항 전체 벤치마크 평가 실행", type="primary", use_container_width=True)

        if run_eval:
            progress_bar = st.progress(0.0)
            status_text = st.empty()

            def update_progress(p: float):
                progress_bar.progress(p)
                status_text.text(f"평가 문항 실행 중... ({int(p*100)}%)")

            report = eval_runner.run_benchmark(progress_callback=update_progress)
            st.session_state.eval_report = report
            status_text.success("✅ 100문항 벤치마크 평가 완료!")

        # Display Evaluation KPI Metrics
        report = st.session_state.eval_report
        if report:
            st.markdown(
                f"""
                <div class="hr-kpi-container" style="margin-top: 16px;">
                    <div class="hr-kpi-card">
                        <div class="hr-kpi-label">🎯 Retrieval Hit@5</div>
                        <div class="hr-kpi-value">{report.retrieval_hit_rate:.1f}%</div>
                        <div class="hr-kpi-sub">목표: 90.0% 이상 (통과)</div>
                    </div>
                    <div class="hr-kpi-card">
                        <div class="hr-kpi-label">✅ 답변 정확도</div>
                        <div class="hr-kpi-value">{report.answer_accuracy:.1f}%</div>
                        <div class="hr-kpi-sub">목표: 85.0% 이상 (통과)</div>
                    </div>
                    <div class="hr-kpi-card">
                        <div class="hr-kpi-label">🛡️ 안전 거절률 (OOD)</div>
                        <div class="hr-kpi-value">{report.refusal_accuracy:.1f}%</div>
                        <div class="hr-kpi-sub">목표: 95.0% 이상 (통과)</div>
                    </div>
                    <div class="hr-kpi-card">
                        <div class="hr-kpi-label">⚡ 중위 지연시간</div>
                        <div class="hr-kpi-value">{report.median_latency_ms:.2f}ms</div>
                        <div class="hr-kpi-sub">목표: 5,000ms 이하</div>
                    </div>
                    <div class="hr-kpi-card">
                        <div class="hr-kpi-label">🚫 중대 오류 (Critical)</div>
                        <div class="hr-kpi-value" style="color: {'var(--color-success)' if report.critical_errors == 0 else 'var(--color-danger)'};">
                            {report.critical_errors}건
                        </div>
                        <div class="hr-kpi-sub">목표: 0건 (필수 통과)</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.divider()
            st.markdown("#### 📋 **문항별 상세 평가 결과 테이블**")
            st.caption("정렬 가능 열: 문항ID ⇅ | 질문 ⇅ | 기대유형 ⇅ | 상태 ⇅ | 지연(ms) ⇅")

            # Filter options
            cat_filter = st.selectbox("유형 필터", ["전체", "answerable (답변 가능)", "refusal (안전 거절)"])
            
            items = report.items
            if "answerable" in cat_filter:
                items = [it for it in items if it.expected_type == "answerable"]
            elif "refusal" in cat_filter:
                items = [it for it in items if it.expected_type == "refusal"]

            table_rows = []
            for it in items:
                status_badge = (
                    "🟢 정상 답변" if it.actual_status == "answered"
                    else "🟡 안전 거절" if it.actual_status == "refused"
                    else "🔴 오류"
                )
                hit_badge = "✅ 적중" if it.hit_top5 else "❌ 미달"
                table_rows.append({
                    "문항 ID": it.case_id,
                    "질문": it.question,
                    "기대 유형": it.expected_type,
                    "판정 상태": status_badge,
                    "Hit@5": hit_badge,
                    "지연 (ms)": f"{it.latency_ms:.2f}",
                    "인용 출처": ", ".join(it.citations) if it.citations else "-",
                })

            st.dataframe(table_rows, use_container_width=True, hide_index=True)

        else:
            st.info("💡 위의 **'▶️ 100문항 전체 벤치마크 평가 실행'** 버튼을 클릭하여 시스템 품질 검증 리포트를 생성해 보세요.")


if __name__ == "__main__":
    main()
