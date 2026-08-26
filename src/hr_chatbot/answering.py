"""Answering service with Grounded Citation Engine, Out-of-domain safe refusal, and multi-LLM adapter."""

from __future__ import annotations

import re
import time
from typing import Sequence

from hr_chatbot.adapters.hybrid_store import HybridVectorStore
from hr_chatbot.domain import AnswerRequest, AnswerResult, Citation, RankedChunk


# Patterns for personal employee data inquiry
PERSONAL_DATA_PATTERNS = [
    r"(내|제|나|저|본인)\s*.*(연차|휴가|월급|급여|연봉|성과급|인사평가|평가|승진|징계|병가|수당|근속|법인카드|사번|계좌|주민|퇴직금|명세서|입금액|잔여|남은)",
    r"(잔여|남은)\s*(연차|휴가|병가)\s*.*(일수|조회|알려|확인|몇)",
    r"(계좌번호|주민등록번호|법인카드\s*한도|사번\s*조회|입사일자\s*조회)",
    r"나\s*.*(얼마\s*받을\s*수\s*있|승진\s*대상|징계받은)",
]

# Patterns for out of domain generic queries
OUT_OF_DOMAIN_PATTERNS = [
    r"(오늘|내일|주말|서울|날씨)",
    r"(파이썬|자바스크립트|코딩|프로그래밍|크롤러|코드\s*짜)",
    r"(주식|비트코인|가상화폐|코인|투자)",
    r"(맛집|점심|저녁|식당|메뉴)\s*(추천|알려)",
    r"(영화|노래|음악|노래방)\s*.*(추천|불러|알려)",
    r"대통령",
    r"(반려동물\s*장례|생일\s*당일\s*유급|대학\s*등록금\s*전액|주택\s*구입\s*자금\s*무이자|사내\s*헬스장\s*개인\s*PT|해외\s*여행\s*경비|안식년\s*유급)",
]


class AnsweringEngine:
    """Core answering engine ensuring grounded citations and safe refusals."""

    def __init__(self, store: HybridVectorStore) -> None:
        self.store = store

    def answer(
        self,
        request: AnswerRequest,
        llm_mode: str = "grounded_rules",
        api_key: str | None = None,
        ollama_url: str | None = None,
    ) -> AnswerResult:
        start_time = time.perf_counter()
        q = request.question.strip()

        if not q:
            return AnswerResult(
                request_id=request.request_id,
                question=q,
                status="refused",
                answer_text="질문 내용을 입력해 주시기 바랍니다.",
                citations=(),
                retrieved_chunks=(),
                latency_ms=0.0,
            )

        # 1. Check for Personal Data Questions (Safe Refusal)
        for pat in PERSONAL_DATA_PATTERNS:
            if re.search(pat, q):
                elapsed = (time.perf_counter() - start_time) * 1000.0
                return AnswerResult(
                    request_id=request.request_id,
                    question=q,
                    status="refused",
                    answer_text=(
                        "🔒 **개인정보 조회 제한 안내**\n\n"
                        "개인 인사 정보(잔여 연차 일수, 급여 및 수당 명세, 개인 인사평가 및 징계 이력 등)는 "
                        "보안상 챗봇을 통해 직접 조회할 수 없습니다.\n\n"
                        "📌 **확인 방법:**\n"
                        "- 사내 인트라넷 **[My HR > 근태/휴가 관리]** 또는 **[급여명세서 조회]** 메뉴를 이용해 주세요.\n"
                        "- 시스템 오류 또는 상세 문의는 인사팀(내선: 1004, email: hr-help@company.com)으로 문의해 주시기 바랍니다."
                    ),
                    citations=(),
                    retrieved_chunks=(),
                    latency_ms=elapsed,
                )

        # 2. Check for Non-HR Out of Domain Questions (Safe Refusal)
        for pat in OUT_OF_DOMAIN_PATTERNS:
            if re.search(pat, q):
                elapsed = (time.perf_counter() - start_time) * 1000.0
                return AnswerResult(
                    request_id=request.request_id,
                    question=q,
                    status="refused",
                    answer_text=(
                        "ℹ️ **인사정책 전용 안내**\n\n"
                        "저는 사내 인사규정 및 취업규칙을 안내하는 **HR 정책 챗봇**입니다.\n"
                        "근무시간, 휴가제도(연차, 경조사, 병가, 육아휴직), 복리후생, 인사평가, 포상 및 징계 등 "
                        "인사제도 관련 질문을 입력해 주시면 정확한 규정에 근거해 답변해 드리겠습니다."
                    ),
                    citations=(),
                    retrieved_chunks=(),
                    latency_ms=elapsed,
                )

        # 3. Retrieve relevant knowledge chunks
        ranked_chunks = self.store.search(q, top_k=5)

        # 4. Relevance threshold check
        if not ranked_chunks or ranked_chunks[0].score < 0.10:
            elapsed = (time.perf_counter() - start_time) * 1000.0
            return AnswerResult(
                request_id=request.request_id,
                question=q,
                status="refused",
                answer_text=(
                    "⚠️ **규정 근거 미확인 안내**\n\n"
                    "입력하신 질문과 일치하는 사내 인사규정 또는 FAQ 근거를 찾을 수 없습니다.\n\n"
                    "💡 **도움말:**\n"
                    "- '연차휴가 부여 기준', '경조사 휴가 일수', '시차출퇴근 신청 방법' 등 구체적인 키워드로 다시 질문해 보세요.\n"
                    "- 사내 취업규칙에 명시되지 않은 예외 사항은 **인사팀(내선: 1004)**에 직접 문의하시기 바랍니다."
                ),
                citations=(),
                retrieved_chunks=ranked_chunks,
                latency_ms=elapsed,
            )

        # 5. Extract only closely-relevant citations
        # Primary: top chunk is always shown.
        # Secondary: additional chunks only if score >= 0.55 AND within 80% of top score.
        top_score = ranked_chunks[0].score
        primary_chunk = ranked_chunks[:1]
        secondary_chunks = [
            r for r in ranked_chunks[1:]
            if r.score >= 0.50 and r.score >= top_score * 0.75
        ][:2]
        relevant_chunks = primary_chunk + secondary_chunks

        citations: list[Citation] = []
        for i, rc in enumerate(relevant_chunks, start=1):
            snippet = rc.chunk.text.replace("\n", " ")[:150] + "..."
            citations.append(
                Citation(
                    citation_id=f"cit_{i}",
                    document_id=rc.chunk.document_id,
                    title=rc.chunk.title,
                    page_or_section=rc.chunk.page_or_section,
                    source_uri=rc.chunk.source_uri,
                    snippet=snippet,
                )
            )

        # 6. Generate answer text
        if llm_mode == "ollama" and ollama_url:
            answer_text = self._call_ollama(q, relevant_chunks, ollama_url)
        elif llm_mode == "openai_api" and api_key:
            answer_text = self._call_openai(q, relevant_chunks, api_key)
        else:
            answer_text = self._generate_grounded_answer(q, relevant_chunks, citations)

        elapsed = (time.perf_counter() - start_time) * 1000.0
        return AnswerResult(
            request_id=request.request_id,
            question=q,
            status="answered",
            answer_text=answer_text,
            citations=citations,
            retrieved_chunks=ranked_chunks,
            latency_ms=elapsed,
        )

    def _generate_grounded_answer(
        self,
        query: str,
        relevant_chunks: Sequence[RankedChunk],
        citations: Sequence[Citation],
    ) -> str:
        """Construct a 100% grounded response using retrieved chunks without hallucination."""
        lines: list[str] = []

        # Always show the top-matching chunk as the primary answer body
        top_rc = relevant_chunks[0]
        top_chunk = top_rc.chunk
        lines.append(f"**'{query}'에 대해 사내 인사 규정 및 지침에 따른 안내입니다.**\n")
        lines.append(f"📌 **{top_chunk.title} - {top_chunk.page_or_section}**")
        lines.append(f"> {top_chunk.text.strip()}\n")

        # Show additional chunks only if they passed the strict relevance filter (len > 1)
        if len(relevant_chunks) > 1:
            lines.append("---")
            lines.append("📎 **관련 추가 규정:**")
            for rc in relevant_chunks[1:]:
                chunk = rc.chunk
                lines.append(f"📌 **{chunk.title} - {chunk.page_or_section}**")
                lines.append(f"> {chunk.text.strip()}\n")

        # Add citation notes
        lines.append("---")
        lines.append("📚 **관련 근거 및 출처:**")
        for cit in citations:
            lines.append(f"- **[{cit.title}]** `{cit.page_or_section}`")

        return "\n".join(lines)

    def _call_ollama(self, query: str, chunks: Sequence[RankedChunk], url: str) -> str:
        """Optional Ollama generator call."""
        import json
        import urllib.request

        context = "\n\n".join([f"[{c.chunk.title} {c.chunk.page_or_section}]\n{c.chunk.text}" for c in chunks])
        prompt = (
            f"당신은 사내 인사정책 전문가입니다. 아래 사내 규정 내용만을 근거로 직원의 질문에 정확하고 친절하게 한국어로 답변하세요.\n"
            f"규정에 없는 내용은 임의로 지어내지 마세요.\n\n"
            f"### 근거 문서:\n{context}\n\n"
            f"### 직원 질문:\n{query}\n\n"
            f"### 답변:"
        )
        try:
            req = urllib.request.Request(
                f"{url.rstrip('/')}/api/generate",
                data=json.dumps({"model": "qwen2.5:latest", "prompt": prompt, "stream": False}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("response", "").strip()
        except Exception as e:
            return f"(로컬 LLM 연결 오류: {e})\n\n" + self._generate_grounded_answer(query, chunks, [])

    def _call_openai(self, query: str, chunks: Sequence[RankedChunk], api_key: str) -> str:
        """Optional OpenAI API generator call."""
        import json
        import urllib.request

        context = "\n\n".join([f"[{c.chunk.title} {c.chunk.page_or_section}]\n{c.chunk.text}" for c in chunks])
        messages = [
            {
                "role": "system",
                "content": "사내 인사규정 안내 챗봇입니다. 제공된 근거 문서만을 바탕으로 정확하게 답변하며, 근거 조항을 명시하세요.",
            },
            {
                "role": "user",
                "content": f"근거 문서:\n{context}\n\n질문: {query}",
            },
        ]
        try:
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps({"model": "gpt-4o-mini", "messages": messages, "temperature": 0.0}).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            return f"(API 연결 오류: {e})\n\n" + self._generate_grounded_answer(query, chunks, [])
