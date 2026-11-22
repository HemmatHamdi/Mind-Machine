"""Local, reviewed passages only; no network, embeddings or external database."""

import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path

KNOWLEDGE_PATH = Path(__file__).with_name("data") / "knowledge.json"
NO_EVIDENCE_REPLY = (
    "مش عندي مصدر رسمي متحقق منه يجاوب السؤال ده حاليًا، ومش هخمن. "
    "راجع المرشد التعليمي في مدرستك أو موقع وزارة التربية والتعليم: "
    "https://moe.gov.eg/"
)
STOP_WORDS = set(
    "ما ماذا هي هو هل في من عن على الي لي انا ايه اي ازاي ممكن عايز "
    "عاوز اريد اعرف البكالوريا المصريه المصرية نظام اشرح ليه كم".split()
)


def tokens(text: str) -> list[str]:
    text = "".join(
        char for char in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(char) and char != "ـ"
    ).translate(str.maketrans({"ى": "ي", "ة": "ه"}))
    return [
        word for word in re.findall(r"[^\W_]+", text)
        if len(word) > 1 and word not in STOP_WORDS
    ]


class KnowledgeBase:
    def __init__(self, data: dict):
        self.passages = [
            {**passage, "source": data["sources"][passage["source_id"]]}
            for passage in data["passages"]
            if passage.get("verified") is True
            and data["sources"][passage["source_id"]]["status"]
            in {"verified", "reviewed_report", "reviewed_copy"}
        ]
        self.documents = [
            Counter(tokens(passage["title"] + " " + passage["text"]))
            for passage in self.passages
        ]

    @classmethod
    def load(cls):
        return cls(json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8")))

    def retrieve(self, question: str) -> list[dict]:
        query = set(tokens(question))
        if not self.documents or len(query) < 2:
            return []
        average_length = sum(map(lambda doc: sum(doc.values()), self.documents)) / len(
            self.documents
        )
        ranked = []
        for passage, document in zip(self.passages, self.documents):
            overlap = query & document.keys()
            if len(overlap) < max(2, math.ceil(len(query) / 2)):
                continue
            score = 0.0
            for term in overlap:
                frequency = sum(term in doc for doc in self.documents)
                idf = math.log(
                    1 + (len(self.documents) - frequency + 0.5) / (frequency + 0.5)
                )
                tf = document[term]
                score += idf * tf * 2.5 / (
                    tf + 1.5 * (0.25 + 0.75 * sum(document.values()) / average_length)
                )
            ranked.append((score, passage))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [passage for _, passage in ranked[:3]]


def cited_reply(reply: str, passages: list[dict]) -> str:
    by_id = {passage["id"]: passage for passage in passages}
    citations = set(re.findall(r"\[([^\[\]\n]+)\]", reply))
    if not citations or not citations <= by_id.keys() or re.search(
        r"https?://|www\.", reply, flags=re.IGNORECASE
    ):
        return NO_EVIDENCE_REPLY
    references = []
    for passage in passages:
        if passage["id"] not in citations:
            continue
        source = passage["source"]
        references.append(
            f"[{passage['id']}] {passage['title']} — {source['title']}\n"
            f"{source['url']}\nآخر مراجعة للمقطع: {passage['checked_on']}"
        )
        references.extend(
            f"رابط للمراجعة: {item['title']}\n{item['url']}"
            for item in source.get("additional_sources", [])
        )
    references = list(dict.fromkeys(references))
    notices = list(dict.fromkeys(
        passage["source"]["notice"]
        for passage in passages
        if passage["id"] in citations
        and passage["source"].get("notice")
    ))
    prefix = "\n".join(notices) + "\n\n" if notices else ""
    return prefix + reply + "\n\nالمصادر:\n" + "\n\n".join(references)
