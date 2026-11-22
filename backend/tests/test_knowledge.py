"""Offline fixtures and regression checks against the reviewed source summaries."""

import asyncio
import copy
import json

import pytest
from fastapi.testclient import TestClient

from gemini_adapter import GeminiAdapter
from knowledge import KNOWLEDGE_PATH, KnowledgeBase, NO_EVIDENCE_REPLY, cited_reply, tokens
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


def test_shipped_corpus_distinguishes_reports_copy_and_pending_sources():
    kb = KnowledgeBase.load()
    assert len(kb.passages) == 15
    assert {p["source_id"] for p in kb.passages} == {
        "maspero_faq_2026_11_12", "gazette_228_2026", "decree_213_2025",
        "cairo_admissions_2026_08_03",
    }
    for passage in kb.passages:
        assert passage["source"]["status"] in {"reviewed_report", "reviewed_copy"}
        assert passage["source"]["notice"]
        assert passage["source"]["checked_on"] == "2026-11-22"
    assert not any(p["source_id"].startswith("ministry") for p in kb.passages)


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
    data = json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    data["passages"] = [
        p for p in data["passages"] if p["source_id"] == "maspero_faq_2026_11_12"
    ]
    assert KnowledgeBase(data).retrieve(question) == []


ENGINEERING_QUESTION = (
    "أنا في تانية ثانوي في مسار الهندسة وعلوم الحاسب. "
    "إيه اختياراتي في مادة التخصص؟ وبختار كام مادة؟"
)


@pytest.mark.parametrize(("question", "passage_id"), [
    (ENGINEERING_QUESTION, "DEG150_G2_PATHS"),
    ("اختيار مادة تخصص مسار الطب وعلوم الحياة", "DEG150_G2_ALL_TRACKS"),
    ("مواد التخصص في الصف الثالث ومسارات البكالوريا", "DEG150_G3_PATHS"),
    ("تغيير مسار البكالوريا عند الوصول إلى الصف الثالث", "DEG150_PATH_SWITCH"),
    ("الطبيعة الاختيارية والمجانية ومدة نظام البكالوريا", "DEG213_SYSTEM"),
    ("قولي مواد سنة أولى بكالوريا", "DEG213_G1_SUBJECTS"),
    ("القبول الجامعي لحاملي البكالوريا وفق التنسيق والمجموع", "CAIRO_UNIVERSITY_ADMISSIONS"),
])
def test_new_source_topics_are_retrieved(question, passage_id):
    assert KnowledgeBase.load().retrieve(question)[0]["id"] == passage_id


def test_scanned_copy_answer_discloses_provenance_and_corroboration():
    passages = KnowledgeBase.load().retrieve(ENGINEERING_QUESTION)
    assert "مادة تخصصية واحدة" in passages[0]["text"]
    assert "الكيمياء أو البرمجة والذكاء الاصطناعي" in passages[0]["text"]
    reply = cited_reply("إجابة تجريبية [DEG150_G2_PATHS]", passages)
    assert "LawHub" in reply
    assert "لم نراجع نسخة رقمية مباشرة" in reply
    assert "https://dspace.id.com.eg/" in reply
    assert "https://www.egyin.com/" in reply
    assert "اليوم السابع" not in reply


@pytest.mark.parametrize("question", [
    "رسوم الإعادة", "درجات قبول جامعة القاهرة 2027", "سعر البيتكوين اليوم",
])
def test_new_sources_do_not_invent_missing_fees_or_cutoffs(question):
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


def test_counselor_questions_are_personalized_without_model_call():
    question = (
        "أنا في تالتة إعدادي وداخل أولى ثانوي وبحب الرسم وبناء المجسمات. "
        "اديني ٣ أسئلة قصيرة أسألهم للمرشد عشان أختار بنفسي المسار المناسب."
    )

    def forbidden(api_key):
        pytest.fail("Generic counselor prompts must not call Gemini")

    adapter = GeminiAdapter(api_key="synthetic-key", client_factory=forbidden)
    reply = asyncio.run(adapter.generate(question))
    assert "الرسم وبناء المجسمات" in reply
    assert reply.count("\n1.") + reply.count("\n2.") + reply.count("\n3.") == 3
    assert "مش ترشيح مني لمسار" in reply
    assert "[FAQ_GUIDANCE]" in reply
    assert "تقرير ماسبيرو" in reply


def test_model_does_not_choose_a_path_for_a_student():
    def forbidden(api_key):
        pytest.fail("A path-choice question must not construct a model client")

    adapter = GeminiAdapter(api_key="synthetic-key", client_factory=forbidden)
    reply = asyncio.run(adapter.generate(
        "أنا بحب الرسم وبناء المجسمات، أي مسار أختار؟"
    ))
    assert reply == NO_EVIDENCE_REPLY


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


def test_authenticated_counselor_questions_use_local_guidance(monkeypatch):
    from approved_main import build_app

    monkeypatch.setenv("GEMINI_EXECUTION_APPROVED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-key")
    monkeypatch.setenv("CHAT_AUTH_USERS", json.dumps({
        "demo": hash_password("synthetic-password-only"),
    }))

    def forbidden(api_key):
        pytest.fail("Counselor question mode must not call Gemini")

    question = (
        "أنا في تالتة إعدادي وبحب الرسم وبناء المجسمات. "
        "اديني ٣ أسئلة أسألهم للمرشد عشان أختار المسار بنفسي."
    )
    with TestClient(build_app(client_factory=forbidden)) as client:
        response = client.post(
            "/chat", json={"message": question},
            auth=("demo", "synthetic-password-only"),
        )
    assert response.status_code == 200
    assert "الرسم وبناء المجسمات" in response.json()["reply"]
    assert "[FAQ_GUIDANCE]" in response.json()["reply"]
    assert "https://www.maspero.eg/" in response.json()["reply"]


def test_authenticated_first_year_subject_question_uses_reviewed_list(monkeypatch):
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
        return SimpleNamespace(output_text=(
            "المواد المضافة: العربية، اللغة الأجنبية الأولى، التاريخ المصري، "
            "الرياضيات، العلوم المتكاملة، الفلسفة والمنطق. وغير المضافة: "
            "التربية الدينية واللغة الأجنبية الثانية والبرمجة والذكاء الاصطناعي. "
            "[DEG213_G1_SUBJECTS]"
        ))

    def factory(api_key):
        return SimpleNamespace(interactions=SimpleNamespace(create=create))

    with TestClient(build_app(client_factory=factory)) as client:
        response = client.post(
            "/chat", json={"message": "قولي مواد سنة أولى بكالوريا"},
            auth=("demo", "synthetic-password-only"),
        )
    assert response.status_code == 200
    reply = response.json()["reply"]
    assert "العلوم المتكاملة" in reply
    assert "https://www.youm7.com/" in reply
    assert "https://moe.gov.eg/" in reply
    assert len(calls) == 1
    evidence = json.loads(calls[0]["input"])["evidence"]
    assert evidence[0]["id"] == "DEG213_G1_SUBJECTS"
    assert "70%" in evidence[0]["text"]


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


def test_engineering_question_through_authenticated_api_with_fake_model(monkeypatch):
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
        return SimpleNamespace(output_text=(
            "بتختار مادة واحدة: الكيمياء أو البرمجة والذكاء الاصطناعي. "
            "[DEG150_G2_PATHS]"
        ))

    def factory(api_key):
        return SimpleNamespace(interactions=SimpleNamespace(create=create))

    with TestClient(build_app(client_factory=factory)) as client:
        response = client.post(
            "/chat", json={"message": ENGINEERING_QUESTION},
            auth=("demo", "synthetic-password-only"),
        )
    assert response.status_code == 200
    reply = response.json()["reply"]
    assert "مادة واحدة" in reply and "LawHub" in reply
    assert "https://www.egyin.com/" in reply
    assert len(calls) == 1
    evidence = json.loads(calls[0]["input"])["evidence"]
    assert evidence[0]["id"] == "DEG150_G2_PATHS"
    assert "لم نراجع نسخة رقمية مباشرة" in evidence[0]["source_note"]
