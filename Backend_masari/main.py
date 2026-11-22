"""Minimal server-side Gemini integration for the Masari Week 5 deliverable."""

import logging
import os
from pathlib import Path
import re
import time
from collections.abc import Callable

import httpx
from dotenv import dotenv_values, load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

from security import ChatSecurity

ENV_FILE = Path(__file__).resolve().with_name(".env")
load_dotenv(ENV_FILE, encoding="utf-8-sig")


def gemini_api_key() -> str:
    names = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    settings = dotenv_values(ENV_FILE, encoding="utf-8-sig")
    return next((value for name in names if (value := (settings.get(name) or "").strip())), "")


GEMINI_CHAT_URL = "https://generativelanguage.googleapis.com/v1beta/models"
# Subject summaries from articles 2 and 3, checked on 2026-11-22.
# The linked text is a secondary reproduction, pending Gazette verification.
SUBJECT_TABLE = """| المسار | مواد الصف الثاني الثانوي (يختار الطالب مادة واحدة) | مواد الصف الثالث الثانوي (يدرس الطالب المادتين) |
| --- | --- | --- |
| الطب وعلوم الحياة | الرياضيات أو الفيزياء | الأحياء (مستوى متقدم) والكيمياء (مستوى متقدم) |
| الهندسة وعلوم الحاسب | الكيمياء أو البرمجة والذكاء الاصطناعي | الرياضيات (مستوى متقدم) والفيزياء (مستوى متقدم) |
| الأعمال | المحاسبة أو إدارة الأعمال | الاقتصاد (مستوى متقدم) والرياضيات |
| الآداب والفنون | علم النفس أو اللغة الأجنبية الثانية | الجغرافيا (مستوى متقدم) والإحصاء |"""
SOURCE_NOTE = "قرأ الفريق النص المنقول على LawHub، ولم يطابقه بعد مع النسخة الرسمية."
PATHWAY_REFERENCE = (
    "مواد التخصص في مسارات البكالوريا المصرية حسب المادتين الثانية والثالثة من القرار 150 لسنة 2026."
    + "\n\n" + SUBJECT_TABLE + "\n\n" + SOURCE_NOTE
)
SOURCE_REGISTER = """[S1] LawHub: Decree 150 of 2026, full text
Third-party copy of an official decree. Full text read. Gives the four pathways, the subjects for grades 2 and 3 of secondary, the 600-mark total, and exam entry rules. Needs comparison with an official copy.
https://lawhub.info/eg/?p=19699

[S2] Egyin: news report on Decree 150 of 2026
News report. Says the decree was published in the Official Gazette. Summary only; page not read in full.
https://www.egyin.com/article/153914/%C2%AB%D8%A7%D9%84%D8%AA%D8%B9%D9%84%D9%8A%D9%85%C2%BB-%D8%AA%D8%B5%D8%AF%D8%B1-%D9%82%D8%B1%D8%A7%D8%B1%D9%8B%D8%A7-%D8%AC%D8%AF%D9%8A%D8%AF%D9%8B%D8%A7-%D8%A8%D8%B4%D8%A3%D9%86-%D9%86%D8%B8%D8%A7%D9%85-%D8%A7%D9%84%D8%A8%D9%83%D8%A7%D9%84%D9%88%D8%B1%D9%8A%D8%A7

[S3] Youm7: Decree 213 of 2025 published in the Gazette
News report. Says the Baccalaureate is optional, free, and three years long, and equals the General Secondary Certificate. Summary only.
https://www.youm7.com/story/2025/9/12/%D8%A7%D9%84%D8%AC%D8%B1%D9%8A%D8%AF%D8%A9-%D8%A7%D9%84%D8%B1%D8%B3%D9%85%D9%8A%D8%A9-%D8%AA%D9%86%D8%B4%D8%B1-%D9%82%D8%B1%D8%A7%D8%B1-%D9%88%D8%B2%D8%A7%D8%B1%D8%A9-%D8%A7%D9%84%D8%AA%D8%B1%D8%A8%D9%8A%D8%A9-%D9%88%D8%A7%D9%84%D8%AA%D8%B9%D9%84%D9%8A%D9%85-%D8%A8%D8%B4%D8%A3%D9%86-%D8%A7%D9%84%D8%A8%D9%83%D8%A7%D9%84%D9%88%D8%B1%D9%8A%D8%A7/7118893

[S4] Ministry of Education: news page on the Baccalaureate proposal
Official ministry site. Describes the January 2025 proposal (7 subjects over two years, 4 pathways). The site blocked automated access, so only the search summary was seen. Older than S1.
https://moe.gov.eg/ar/what-s-on/news/baccalau/

[S5] Cairo Governorate portal: university admission for Baccalaureate graduates
Official government portal. Reports a Ministry statement (August 2026) that admission follows the same coordination system as the General Secondary Certificate. Summary only.
https://www.cairo.gov.eg/en/news/2026/august/3/education/"""

GUIDE_INSTRUCTIONS = """You are Masari, a guide for Egyptian Grade 9 students and families.
Respond briefly in the user's language. For questions about pathway facts, use only the
project notes below. Cite facts with short markers like [S1]. The server appends links.
For general guidance give two short sentences or three brief bullets. When a parent
asks how to choose, suggest a question to ask the student and a next step.
Use the full Arabic grade names exactly as in the table. Never call S1 officially verified. The specialist subject table comes from S1. State how far each cited source was checked.
Attribute S5 to the reported August 2026 statement. Do not infer admission thresholds.
Use S4 only as a historical proposal; do not use it to override S1. If asked for the
sources, list their titles, bracketed IDs and review status. You have no live browsing.
Distinguish specialist subjects from the full curriculum. If asked for an undocumented
rule, say it is unverified and suggest checking with the school. In Egyptian Arabic, حاسبات refers by default to the university faculty. When asked about a route to that college, discuss only documented school pathways and admission limits. For a school student comparing named pathways or asking for questions for their counselor, answer the requested task directly. Use their stated interests, respect corrections, give the requested number of questions and explain each when asked. Before giving facts, resolve the education level. When a phrase could name a university
degree or a school pathway, ask one clarifying question and wait. For clearly unrelated
requests, briefly explain Masari's scope and offer a relevant question. University
curricula are outside scope. University admission questions may use S5 only within
its documented limits. Never cite a school source for a university curriculum.
For mixed requests, answer only the educational part. Briefly identify any unrelated part as outside scope. Never recommend products or prices. Give parent-specific advice only when relevant.
For an ambiguous comparison ask which pathways are meant. For brainstorming, give practical questions
without inventing official rules. Never choose on behalf of a student or promise admission.
""" + PATHWAY_REFERENCE + "\n\n" + SOURCE_REGISTER

SOURCE_LINKS = dict(re.findall(r"^\[(S[1-5])\][^\n]*\n[^\n]*\n(https?://\S+)", SOURCE_REGISTER, re.M))


def clarify_computing_scope(message: str) -> str | None:
    text = re.sub(r"[\u064b-\u065fـ]", "", message.lower())
    text = re.sub("[أإآ]", "ا", text).replace("ى", "ي")
    computing = re.search(r"حاسبات|علوم (?:ال)?حاسب|computer science|computing", text)
    college = re.search(r"كلي[ةه]|جامع[ةهي]|university|college|degree", text)
    studies = re.search(r"هدرس|بدرس|ادرس|بتدرس|هندرس|مواد|مقرر|منهج|مناهج|curricul|courses|study", text)
    admission = re.search(r"تنسيق|قبول|مجموع|ادخل|التحق|admission|apply", text)
    school = re.search(
        r"بكالوريا|ثانوي|مسار|اعدادي|للمرشد|المرشد المدرسي|الهندس[ةه] وعلوم (?:ال)?حاسب"
        r"|baccalaureate|pathway|secondary|grade (?:9|nine)|school counsel", text
    )
    arabic = bool(re.search(r"[ء-ي]", text))
    faculty = bool(re.search(r"\b(?:ال)?حاسبات\b", text))
    named_path = re.search(r"مسار\s+(?:ال)?حاسبات|مسار الهندس[ةه] وعلوم (?:ال)?حاسب", text)
    if faculty and (studies or text.strip(" ؟?!.") == "حاسبات") and not admission and not named_path and (not school or college):
        return ("حاسبات هنا معناها كلية الحاسبات في الجامعة. لمعرفة المواد اللي هتدرسها، "
                "راجع الخطة الدراسية للكلية في جامعتك، لأن المقررات بتختلف حسب الجامعة والبرنامج. "
                "أقدر أساعدك تقارن بين مسارات البكالوريا لو ده جزء من استعدادك للكلية.")
    if college and studies and not admission and not school:
        return ("مواد الكلية بتختلف حسب الجامعة والبرنامج. تقدر تراجع الخطة الدراسية المنشورة للكلية في جامعتك. "
                "أقدر أساعدك تقارن مواد مسارات البكالوريا المصرية."
                if arabic else "For university courses, check the curriculum for your university and degree. I can explain the Egyptian Baccalaureate pathways.")
    if computing and studies and not school and not college and not admission:
        return ("تقصد مواد كلية الحاسبات في الجامعة، ولا مواد مسار الهندسة وعلوم الحاسب في البكالوريا المصرية؟"
                if arabic else "Do you mean a university computer science degree or the Egyptian Baccalaureate engineering and computing pathway?")
    return None


def asks_for_subject_overview(message: str) -> bool:
    text = re.sub(r"[\u064b-\u065fـ]", "", message.strip()).strip("؟?!. ")
    text = re.sub("[أإآ]", "ا", text)
    return bool(re.fullmatch(
        r"(?:(?:ايه(?: هي)?|ما(?: هي)?|ماهي|عايز اعرف|اعرض(?: لي)?|وريني)\s+)?"
        r"(?:جدول\s+)?مواد\s+(?:التخصص\s+(?:في |لكل )?)?"
        r"(?:كل مسار|المسارات(?: الاربعة)?|كل المسارات|مسارات البكالوريا)"
        r"(?: في البكالوريا(?: المصرية)?)?", " ".join(text.split())
    ))


def normalize_arabic(text: str) -> str:
    text = re.sub(r"[\u064b-\u065fـ]", "", text.lower())
    return re.sub("[أإآ]", "ا", text).replace("ى", "ي").strip()


INTRODUCTION = (
    "أهلًا، أنا مساري. بساعد طلاب الصف الثالث الإعدادي اللي داخلين نظام البكالوريا المصرية "
    "يفهموا المسارات ويقارنوا بينها علشان يختاروا المسار الأنسب لاهتماماتهم. "
    "تقدر تسألني عن النظام ومواد كل مسار، وهجاوبك من المصادر المتاحة عندي. "
    "لو المعلومة مش مؤكدة هقولك، والاختيار النهائي ليك."
)


def asks_for_introduction(message: str) -> bool:
    text = normalize_arabic(message)
    return bool(re.fullmatch(
        r"(?:اهلا(?: يا مساري)?[،, .]*|يا مساري[،, .]*)?"
        r"(?:ممكن |لو سمحت )?(?:عرف نفسك|عرفني (?:بنفسك|بيك|بك)|انت مين|مين انت)"
        r"(?: في جملتين)?[؟?!.،, ]*"
        r"(?:تقدر تساعدني في ايه(?: وايه حدودك)?[؟?!. ]*)?", text
    ))


def split_shopping_request(message: str) -> tuple[str, str]:
    # Keep punctuation inside educational questions unless a shopping clause is found.
    clauses = re.split(r"[؟?!.،,؛;\n]+|\s+(?:وكمان|وبرضه|وبرضو|وبالمرة|and also|and)\s+|\s+و(?=رشح|اقترح|عايز اشتري)", message, flags=re.I)
    kept = []
    for clause in clauses:
        clause = clause.strip()
        text = normalize_arabic(clause)
        product = re.search(r"موبايل|تليفون|هاتف|لابتوب|لاب توب|smartphone|phone|laptop", text)
        shopping = re.search(r"رشح|ترشح|اقترح|اشتري|اشتريه|شراء|سعر|اسعار|recommend|buy|price", text)
        if product and shopping:
            continue
        if clause:
            kept.append(clause)
    if len(kept) == sum(bool(c.strip()) for c in clauses):
        return message, ""
    notice = ("ترشيح أجهزة للشراء خارج نطاق مساري. أقدر أساعدك في أسئلة البكالوريا المصرية."
              if re.search(r"[ء-ي]", message) else
              "Product recommendations are outside Masari’s scope. I can help with the Egyptian Baccalaureate.")
    return "؟ ".join(kept), notice


def subject_reply(question: str) -> str | None:
    normalized = " ".join(normalize_arabic(question).strip(" ؟?!.").split())
    if re.fullmatch(
        r"(?:(?:ايه(?: هي)?|ما هي|ماهي|قولي|قول لي|اذكر|عايز اعرف) )?"
        r"(?:اسماء )?(?:المسارات|مسارات البكالوريا)"
        r"(?: (?:الموجود[ةه]|المتاح[ةه]|الاربع[ةه]))?(?: في البكالوريا)?(?: المصري[ةه])?",
        normalized,
    ):
        names = [row.split("|")[1].strip() for row in SUBJECT_TABLE.splitlines()[2:]]
        return ("مسارات البكالوريا المصرية حسب مصدر المشروع [S1]:\n\n"
                + "\n".join("- " + name for name in names)
                + "\n\n" + SOURCE_NOTE + "\n\n[S1] " + SOURCE_LINKS["S1"])
    if asks_for_subject_overview(question):
        answer = PATHWAY_REFERENCE
    else:
        text = normalize_arabic(question).strip("؟?!. ")
        for row in SUBJECT_TABLE.splitlines()[2:]:
            name, second, third = [cell.strip() for cell in row.strip("|").split("|")]
            pattern = (r"(?:(?:ايه(?: هي)?|ما هي|عايز اعرف)\s+)?مواد\s+(?:مسار\s+)?"
                       + re.escape(normalize_arabic(name))
                       + r"(?: في البكالوريا(?: المصري[ةه])?)?")
            if re.fullmatch(pattern, " ".join(text.split())):
                answer = (f"**مواد التخصص في مسار {name}** [S1]\n\n"
                          f"- الصف الثاني الثانوي (اختيار مادة واحدة): {second}.\n"
                          f"- الصف الثالث الثانوي (يدرس الطالب المادتين): {third}.\n\n{SOURCE_NOTE}")
                break
        else:
            return None
    return answer + "\n\n[S1] " + SOURCE_LINKS["S1"]


def length_fallback(question: str) -> str:
    """Return a labeled local recovery message if generation ends early."""
    if re.search(r"[ء-ي]", question):
        if "مسار" in question and any(word in question for word in ("نختار", "اختار", "أختار", "اختيار", "أحسن", "احسن", "أنسب")):
            return (
                "من مساري (الرد الآلي لم يكتمل): اسألوا الطالب: إيه أكتر مادتين بتحبهم، وإيه اللي بتحبه فيهم؟ "
                "اختاروا معاه مسارين يستكشفهم، وقارنوا مواد كل واحد مع المرشد. القرار في الآخر للطالب وأسرته. "
                "تقدر تكتب: قارن بين مسار الأعمال ومسار الآداب والفنون في تانية ثانوي."
            )
        return "من مساري: الرد الآلي لم يكتمل. جرّب سؤالاً محدداً عن مسار واحد وصف دراسي واحد."
    return "Masari: The model stopped before finishing. Try asking about one pathway and one school year."


MAX_MESSAGE_LENGTH = 4_000
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)

    @field_validator("message")
    @classmethod
    def reject_whitespace_only(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be empty")
        return value.strip()


def create_app(
    transport: httpx.AsyncBaseTransport | None = None,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> FastAPI:
    app = FastAPI(
        title="Masari Week 5 AI API",
        description="A minimal backend endpoint that sends a message to Gemini.",
        version="1.0.0",
    )
    app.state.gemini_transport = transport

    @app.get("/", response_class=HTMLResponse)
    async def demo_page():
        # The HTML page uses the same-origin /chat endpoint, avoiding CORS.
        return Path(__file__).with_name("index.html").read_text(encoding="utf-8")

    @app.get("/health")
    async def health():
        # Does not make an AI call or expose credentials.
        return {"status": "ok"}
    security = ChatSecurity(clock=clock)

    @app.middleware("http")
    async def protect_chat(request, call_next):
        # Authenticate and reserve a per-user slot before parsing the body,
        # including malformed JSON. Never trust a client-supplied user/IP header.
        path = request.scope["path"]
        root_path = request.scope.get("root_path", "").rstrip("/")
        if root_path and path.startswith(root_path + "/"):
            path = path[len(root_path):]
        if request.method == "POST" and path.rstrip("/") == "/chat":
            try:
                await security.check_request(request)
            except HTTPException as exc:
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers={**(exc.headers or {}), "Cache-Control": "no-store"},
                )
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request, exc: RequestValidationError):
        # FastAPI's default response includes the submitted input.
        # Keep validation details useful without echoing user messages.
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
                    for error in exc.errors()
                ]
            },
        )

    # The route also enforces security as defense in depth for mounted apps.
    # Request state prevents a second password check or quota reservation.
    @app.post(
        "/chat",
        dependencies=[Depends(security.scheme), Depends(security.check_request)],
    )
    async def chat(request: ChatRequest) -> dict[str, str]:
        question, notice = split_shopping_request(request.message)
        if not question:
            return {"reply": notice}

        def result(reply: str) -> dict[str, str]:
            return {"reply": reply + ("\n\n" + notice if notice else "")}

        local = INTRODUCTION if asks_for_introduction(question) else (
            clarify_computing_scope(question) or subject_reply(question)
        )
        if local:
            return result(local)
        api_key = gemini_api_key()
        model = os.getenv("GEMINI_MODEL", "").strip() or "gemini-3.8-flash"
        timeout_text = os.getenv("GEMINI_TIMEOUT_SECONDS", "30")
        max_tokens_text = os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "1024")

        if not api_key:
            raise HTTPException(
                status_code=503,
                detail="مفتاح Gemini غير موجود. أضف GEMINI_API_KEY في ملف .env بجوار main.py ثم أعد تشغيل السيرفر.",
            )
        # This is an operator acknowledgement, not a billing-status API check.
        # Never send inference until the account's Free plan has been confirmed.
        if os.getenv("GEMINI_FREE_PLAN_CONFIRMED", "").strip().lower() != "true":
            raise HTTPException(
                status_code=503,
                detail="AI service is disabled until the administrator confirms the Gemini Free plan.",
            )
        if len(model) > 200 or not re.fullmatch(
            r"gemini-[a-z0-9.-]*flash[a-z0-9.-]*", model
        ):
            raise HTTPException(
                status_code=503,
                detail="GEMINI_MODEL must be a model ID, not a URL or routing policy.",
            )
        try:
            timeout_seconds = float(timeout_text)
            if not 1 <= timeout_seconds <= 120:
                raise ValueError
        except ValueError:
            raise HTTPException(
                status_code=503,
                detail="GEMINI_TIMEOUT_SECONDS must be between 1 and 120.",
            ) from None
        try:
            max_tokens = int(max_tokens_text)
            if not 1 <= max_tokens <= 1_024:
                raise ValueError
        except ValueError:
            raise HTTPException(
                status_code=503,
                detail="GEMINI_MAX_OUTPUT_TOKENS must be an integer between 1 and 1024.",
            ) from None

        payload = {
            "systemInstruction": {"parts": [{"text": GUIDE_INSTRUCTIONS}]},
            "contents": [{"role": "user", "parts": [{"text": question}]}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        }
        headers = {"x-goog-api-key": api_key}
        url = f"{GEMINI_CHAT_URL}/{model}:generateContent"

        started = time.monotonic()
        try:
            # HTTPX does not retry by default. Do not follow redirects carrying
            # credentials, select another provider, or request paid flex tiers.
            async with httpx.AsyncClient(
                timeout=timeout_seconds,
                transport=app.state.gemini_transport,
                follow_redirects=False,
            ) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException:
            logger.warning("Gemini timeout elapsed_seconds=%.3f", time.monotonic() - started)
            raise HTTPException(
                status_code=504,
                detail="The AI service timed out. No automatic retry was made.",
            ) from None
        except httpx.RequestError:
            logger.warning("Gemini network failure elapsed_seconds=%.3f", time.monotonic() - started)
            raise HTTPException(
                status_code=502,
                detail="The AI service could not be reached. No automatic retry was made.",
            ) from None

        # Retain useful status/timing diagnostics, never headers, bodies, or
        # exception strings (which could contain credentials or prompt text).
        logger.info(
            "Gemini response status=%d elapsed_seconds=%.3f",
            response.status_code,
            time.monotonic() - started,
        )
        if response.status_code in (401, 403):
            raise HTTPException(
                status_code=503,
                detail="AI service authentication or access failed. Contact the administrator.",
            )
        if response.status_code == 402:
            raise HTTPException(
                status_code=503,
                detail="AI service free allowance is unavailable. Paid fallback is disabled.",
            )
        if response.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail="AI service rate or free usage limit reached. Please try again later.",
            )
        if response.status_code == 404:
            raise HTTPException(
                status_code=503,
                detail="The configured AI model is unavailable. Contact the administrator.",
            )
        if response.status_code == 503:
            raise HTTPException(
                status_code=503,
                detail="The AI provider is temporarily unavailable. Please try again later.",
            )
        if response.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail="The AI service rejected the request or returned an error.",
            )

        try:
            body = response.json()
            if body.get("promptFeedback", {}).get("blockReason"):
                raise HTTPException(status_code=422, detail="Gemini blocked this prompt. Please rephrase.")
            candidate = body["candidates"][0]
            finish = candidate.get("finishReason")
            if finish == "MAX_TOKENS":
                return result(length_fallback(question))
            if finish in {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "RECITATION"}:
                raise HTTPException(status_code=422, detail="Gemini withheld this reply. Please rephrase.")
            parts = candidate.get("content", {}).get("parts", [])
            reply = "".join(
                part["text"] for part in parts
                if not part.get("thought") and isinstance(part.get("text"), str)
            ).strip() if finish == "STOP" else ""
        except (ValueError, IndexError, KeyError, TypeError, AttributeError):
            reply = ""

        if not reply:
            raise HTTPException(
                status_code=502,
                detail="The AI service did not return a complete text reply.",
            )

        cited = dict.fromkeys(re.findall(r"\[(S[1-5])\]", reply))
        links = [f"[{key}] {SOURCE_LINKS[key]}" for key in cited if SOURCE_LINKS[key] not in reply]
        if links:
            reply += "\n\n" + "\n".join(links)
        return result(reply)

    return app


app = create_app()
