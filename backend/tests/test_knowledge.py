"""All education claims here are fictional fixtures, not Baccalaureate rules."""

import asyncio
import copy
import json

import pytest
from fastapi.testclient import TestClient

from gemini_adapter import GeminiAdapter
from knowledge import KnowledgeBase, NO_EVIDENCE_REPLY, cited_reply, tokens
from security import hash_password


def fixture_data():
    return {
        "sources": {
            "fictional": {
                "status": "verified", "title": "Fictional document for tests only",
                "url": "https://example.invalid/fictional",
            },
        },
        "passages": [{
            "id": "TEST1", "source_id": "fictional", "verified": True,
            "checked_on": "2026-11-22", "title": "المسار التجريبي",
            "text": "المسار التجريبي يتضمن أنشطة خيالية للبحث فقط.",
        }],
    }


def test_arabic_diacritics_and_letter_variants_match():
    assert tokens("أَنْشِطَة إختياريّة") == tokens("انشطه اختياريه")
    kb = KnowledgeBase(fixture_data())
    assert kb.retrieve("المَسَار التَّجريبي")[0]["id"] == "TEST1"


@pytest.mark.parametrize("question", [
    "مرحبا", "نظام البكالوريا المصرية", "سعر البيتكوين اليوم",
    "ما هي شروط القبول في كلية الطب؟", "كم مجموع البكالوريا؟",
    "المسار", "معلومات عن البكالوريا", "المسار التجريبي وأسعار الذهب والبيتكوين والسفر",
])
def test_unsupported_or_weak_questions_have_no_evidence(question):
    assert KnowledgeBase(fixture_data()).retrieve(question) == []


@pytest.mark.parametrize("target", ["source", "passage"])
def test_unverified_source_or_passage_is_never_retrieved(target):
    data = copy.deepcopy(fixture_data())
    if target == "source":
        data["sources"]["fictional"]["status"] = "pending"
    else:
        data["passages"][0]["verified"] = False
    assert KnowledgeBase(data).retrieve("المسار التجريبي") == []


def test_bm25_returns_at_most_three_passages():
    data = fixture_data()
    for index in range(2, 6):
        passage = dict(data["passages"][0], id=f"TEST{index}")
        data["passages"].append(passage)
    assert len(KnowledgeBase(data).retrieve("المسار التجريبي")) == 3


def test_only_cited_reviewed_links_and_dates_are_appended():
    passages = KnowledgeBase(fixture_data()).retrieve("المسار التجريبي")
    reply = cited_reply("رد خيالي [TEST1]", passages)
    assert "https://example.invalid/fictional" in reply
    assert "2026-11-22" in reply
    assert "Fictional document" in reply


@pytest.mark.parametrize("reply", [
    "جواب بلا مصدر", "جواب [UNKNOWN]", "جواب [TEST1] [UNKNOWN]",
    "جواب [TEST1] https://invented.invalid",
    "جواب [TEST1] www.invented.invalid",
])
def test_missing_unretrieved_citations_or_model_links_are_rejected(reply):
    passages = KnowledgeBase(fixture_data()).retrieve("المسار التجريبي")
    assert cited_reply(reply, passages) == NO_EVIDENCE_REPLY


def test_shipped_corpus_distinguishes_report_from_pending_decrees():
    kb = KnowledgeBase.load()
    assert len(kb.passages) == 7
    assert {p["source_id"] for p in kb.passages} == {"maspero_faq_2026_11_12"}
    for passage in kb.passages:
        assert passage["source"]["status"] == "reviewed_report"
        assert "وليس نص القرار الأصلي" in passage["source"]["notice"]
    assert kb.retrieve("ما هي مسارات البكالوريا المصرية؟") == []


@pytest.mark.parametrize(("question", "passage_id"), [
    ("كيف يتم تقييم الثقافة المالية؟", "FAQ_FINANCE"),
    ("هل أقدر أغير اللغة الأجنبية الثانية؟", "FAQ_LANGUAGE"),
    ("متى لقاءات المرشد التعليمي في أولى ثانوي؟", "FAQ_GUIDANCE"),
    ("امتحان المحاسبة وإدارة الأعمال بالعربية", "FAQ_ARABIC"),
    ("نسبة الحضور والغياب في الصف الثاني", "FAQ_ATTENDANCE"),
    ("مشروع الصف الثاني وتقييمه", "FAQ_PROJECT"),
    ("التحاق الراسب بالصف الثاني بالبكالوريا", "FAQ_TRANSFER"),
])
def test_report_faq_topics_are_retrieved(question, passage_id):
    assert KnowledgeBase.load().retrieve(question)[0]["id"] == passage_id


@pytest.mark.parametrize("question", [
    "كم عدد مواد البكالوريا؟", "ما هي رسوم الإعادة؟",
    "ما هي كليات مسار الأعمال؟", "هل الطب أفضل من الهندسة؟",
])
def test_report_does_not_cover_all_rules_or_admissions(question):
    assert KnowledgeBase.load().retrieve(question) == []


def test_reviewed_report_always_has_a_visible_attribution():
    kb = KnowledgeBase.load()
    passages = kb.retrieve("تقييم الثقافة المالية")
    reply = cited_reply("إجابة وهمية للاختبار [FAQ_FINANCE]", passages)
    assert reply.startswith("بحسب تقرير ماسبيرو")
    assert "12 نوفمبر 2026" in reply
    assert "وليس نص القرار الأصلي" in reply
    assert "https://www.maspero.eg/" in reply


def test_no_evidence_means_no_provider_client():
    def forbidden(api_key):
        pytest.fail("No evidence must never construct a provider client")

    adapter = GeminiAdapter(
        api_key="synthetic-key", client_factory=forbidden,
        knowledge=KnowledgeBase(fixture_data()),
    )
    assert asyncio.run(adapter.generate("ما هي شروط كلية الطب؟")) == NO_EVIDENCE_REPLY


def test_authenticated_unsupported_chat_returns_handover_without_network(
    monkeypatch,
):
    from approved_main import build_app

    monkeypatch.setenv("GEMINI_EXECUTION_APPROVED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-key")
    monkeypatch.setenv("CHAT_AUTH_USERS", json.dumps({
        "demo": hash_password("synthetic-password-only"),
    }))
    monkeypatch.setenv("CHAT_RATE_LIMIT_REQUESTS", "2")
    monkeypatch.setenv("CHAT_RATE_LIMIT_WINDOW_SECONDS", "60")

    def forbidden(api_key):
        pytest.fail("The shipped corpus must not trigger a model call")

    with TestClient(build_app(client_factory=forbidden)) as client:
        assert client.post(
            "/chat", json={"message": "ما هي مسارات البكالوريا؟"},
        ).status_code == 401
        for _ in range(2):
            response = client.post(
                "/chat", json={"message": "ما هي مسارات البكالوريا؟"},
                auth=("demo", "synthetic-password-only"),
            )
            assert response.status_code == 200
            assert response.json() == {"reply": NO_EVIDENCE_REPLY}
            assert response.headers["cache-control"] == "no-store"
        assert client.post(
            "/chat", json={"message": "ما هي مسارات البكالوريا؟"},
            auth=("demo", "synthetic-password-only"),
        ).status_code == 429


def test_authenticated_report_question_sends_evidence_to_fake_model(monkeypatch):
    from types import SimpleNamespace
    from approved_main import build_app

    monkeypatch.setenv("GEMINI_EXECUTION_APPROVED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-key")
    monkeypatch.setenv("CHAT_AUTH_USERS", json.dumps({
        "demo": hash_password("synthetic-password-only"),
    }))
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output_text="رد وهمي لاختبار الربط [FAQ_GUIDANCE]")

    def factory(api_key):
        return SimpleNamespace(interactions=SimpleNamespace(create=create))

    with TestClient(build_app(client_factory=factory)) as client:
        response = client.post(
            "/chat", json={"message": "متى لقاءات المرشد التعليمي في أولى ثانوي؟"},
            auth=("demo", "synthetic-password-only"),
        )
    assert response.status_code == 200
    assert response.json()["reply"].startswith("بحسب تقرير ماسبيرو")
    assert "وليس نص القرار الأصلي" in response.json()["reply"]
    assert len(calls) == 1
    evidence = json.loads(calls[0]["input"])["evidence"]
    assert evidence[0]["id"] == "FAQ_GUIDANCE"
    assert "وليس نص القرار الأصلي" in evidence[0]["source_note"]
