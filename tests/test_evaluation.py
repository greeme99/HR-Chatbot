"""Tests for Evaluation and Benchmark KPI Report."""

from pathlib import Path
import pytest
from hr_chatbot.adapters.document_parser import DocumentParser
from hr_chatbot.adapters.hybrid_store import HybridVectorStore
from hr_chatbot.answering import AnsweringEngine
from hr_chatbot.evaluation import BenchmarkRunner, get_default_evaluation_dataset

HR_RULES_DIR = Path("docs/HR-Rules")


def test_evaluation_benchmark_run() -> None:
    parser = DocumentParser()
    store = HybridVectorStore()

    for p in HR_RULES_DIR.glob("*.*"):
        if p.suffix.lower() in (".pdf", ".docx", ".csv"):
            try:
                _, chunks = parser.parse_file(p)
                store.add_chunks(chunks)
            except Exception:
                pass

    engine = AnsweringEngine(store)
    runner = BenchmarkRunner(engine)

    dataset = get_default_evaluation_dataset()
    assert len(dataset) == 100

    # Run on a sample subset for fast test execution
    sample_dataset = dataset[:10] + dataset[70:80]
    report = runner.run_benchmark(sample_dataset)

    assert report.total_count == 20
    assert report.retrieval_hit_rate >= 80.0
    assert report.critical_errors == 0
    assert report.median_latency_ms >= 0.0
