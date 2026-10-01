"""Generate JSON sample records from OpenAPI schemas.

Each value is chosen, in order, from: ``const`` / ``enum`` / ``examples`` in
the schema, the string ``format``, field-name heuristics (email, phone, VIN,
plate, address, ...), then the plain type — always within min/max bounds.

Long free-text fields are collected as *slots* and filled by an LLM in one
batched call per chunk. Each slot carries the field meaning (hints file >
schema description > field name), the owning model, the endpoints using it
and the surrounding record, so the generated text fits the data around it.
Without an LLM, slots keep a placeholder sentence.
"""

from __future__ import annotations

import copy
import json
import random
import re
import string
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from llm import LLMConfig, LLMError, complete_json
from openapi import Model, ref_name

LONG_TEXT_NAME_RE = re.compile(
    r"(description|content|note|comment|message|summary|terms|detail|bio|body|instruction|feedback|review|remark)",
    re.I,
)
LONG_TEXT_MIN_LENGTH = 200  # a string field with maxLength >= this is treated as long text
# Field names that have their own generator; never auto-detected as long text.
STRUCTURED_NAME_RE = re.compile(
    r"(address|email|phone|hotline|mobile|url|avatar|image|link|name|plate|vin|nationalid|cccd|color|"
    r"version|token|hash|status|time|date|ward|district|province|city|region|id$|code$)"
)
MAX_DEPTH = 6
LLM_BATCH_SIZE = 25

_LAST = ["Nguyen", "Tran", "Le", "Pham", "Hoang", "Vu", "Dang", "Bui", "Do", "Ngo"]
_MIDDLE = ["Van", "Thi", "Minh", "Hoang", "Thanh", "Duc", "Ngoc", "Quang"]
_FIRST = ["An", "Binh", "Cuong", "Dung", "Ha", "Khoa", "Lan", "Mai", "Nam", "Phuong", "Tuan", "Trang", "Vy"]
_STREETS = ["Le Loi", "Nguyen Hue", "Tran Hung Dao", "Ly Thai To", "Hai Ba Trung", "Dien Bien Phu", "Nguyen Van Linh"]
_WARDS = ["Ben Nghe", "Tan Phong", "Hang Trong", "Dich Vong", "Thach Thang", "An Hai Bac"]
_DISTRICTS = ["Quan 1", "Quan 7", "Hoan Kiem", "Cau Giay", "Hai Chau", "Ninh Kieu"]
_PROVINCES = ["Ha Noi", "TP. Ho Chi Minh", "Da Nang", "Hai Phong", "Can Tho", "Khanh Hoa"]
_COLORS = ["White", "Black", "Blue", "Red", "Silver", "Grey"]
_WORDS = "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore".split()
_VIN_CHARS = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"  # no I, O, Q
_LANGUAGES = {"vi": "Vietnamese", "en": "English"}

# (name fragment, (low, high), decimals or None for integers) — used when the schema has no bounds
_NUMBER_HINTS: list[tuple[str, tuple[float, float], int | None]] = [
    ("latitude", (8.5, 23.4), 6),
    ("longitude", (102.1, 109.5), 6),
    ("dayofweek", (1, 7), None),
    ("year", (2018, 2026), None),
    ("month", (1, 12), None),
    ("percent", (0, 100), None),
    ("price", (50_000, 5_000_000), None),
    ("amount", (50_000, 5_000_000), None),
    ("cost", (50_000, 5_000_000), None),
    ("km", (0, 150_000), None),
    ("mileage", (0, 150_000), None),
    ("kwh", (30, 120), 1),
    ("kw", (50, 300), 1),
    ("count", (0, 20), None),
    ("total", (1, 50), None),
    ("attempt", (0, 5), None),
    ("slot", (0, 10), None),
]


@dataclass
class TextSlot:
    id: str
    owner: str  # component name of the model that owns the field
    field: str
    meaning: str
    max_length: int | None
    target: dict[str, Any]  # the object holding the field; filled in place


def _norm(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def _unwrap(schema: dict[str, Any]) -> dict[str, Any]:
    """``anyOf: [X, {type: null}]`` -> ``X`` (merged with outer description)."""
    for key in ("anyOf", "oneOf"):
        options = [s for s in schema.get(key, []) if s.get("type") != "null"]
        if len(options) == 1:
            return {**{k: v for k, v in schema.items() if k != key}, **options[0]}
    return schema


def _make_faker(locale: str, seed: int | None):
    try:
        from faker import Faker  # optional dependency
    except ImportError:
        return None
    fake = Faker(locale)
    if seed is not None:
        fake.seed_instance(seed)
    return fake


class MockGenerator:
    def __init__(
        self,
        models: dict[str, Model],
        endpoint_summaries: dict[str, str],
        *,
        seed: int | None = None,
        locale: str = "vi_VN",
        llm_fields: list[str] | None = None,
        hints: dict[str, str] | None = None,
        overrides: dict[str, Any] | None = None,
        auto_long_text: bool = True,
    ) -> None:
        self.models = models
        self.endpoint_summaries = endpoint_summaries
        self.rng = random.Random(seed)
        self.faker = _make_faker(locale, seed)
        self.llm_fields = {f.lower() for f in (llm_fields or [])}
        self.hints = hints or {}
        # {"field" | "Model.field": value} — fixed values for rules the schema cannot express.
        self.overrides = {k.lower(): v for k, v in (overrides or {}).items()}
        self.auto_long_text = auto_long_text
        self.slots: list[TextSlot] = []
        self._seq = 0

    # ------------------------------------------------------------------ records
    def generate(self, model: Model, count: int) -> list[Any]:
        return [self._value(model.schema, "", model.name, 0) for _ in range(count)]

    def _value(self, schema: Any, key: str, owner: str, depth: int) -> Any:
        if not isinstance(schema, dict) or depth > MAX_DEPTH:
            return None
        if "$ref" in schema:
            target = self.models.get(ref_name(schema["$ref"]))
            return self._value(target.schema, key, target.name, depth + 1) if target else None
        if "const" in schema:
            return schema["const"]
        if schema.get("enum"):
            return self.rng.choice(schema["enum"])
        examples = schema.get("examples") or ([schema["example"]] if "example" in schema else None)
        if isinstance(examples, list) and examples:
            return copy.deepcopy(self.rng.choice(examples))
        for combo in ("anyOf", "oneOf", "allOf"):
            if combo in schema:
                options = [s for s in schema[combo] if s.get("type") != "null"] or schema[combo]
                return self._value(options[0], key, owner, depth)

        typ = schema.get("type")
        if isinstance(typ, list):
            typ = next((t for t in typ if t != "null"), "null")
        if typ == "object" or "properties" in schema:
            return self._object(schema, owner, depth)
        if typ == "array":
            low = schema.get("minItems", 1)
            high = schema.get("maxItems", low + 2)
            count = self.rng.randint(low, max(low, min(high, low + 2)))
            return [self._value(schema.get("items", {}), key, owner, depth + 1) for _ in range(count)]
        if typ == "string":
            return self._string(schema, key)
        if typ in ("integer", "number"):
            return self._number(schema, key, typ == "integer")
        if typ == "boolean":
            return self.rng.random() < 0.5
        return None

    def _object(self, schema: dict[str, Any], owner: str, depth: int) -> dict[str, Any]:
        props = schema.get("properties", {})
        if not props:
            extra = schema.get("additionalProperties")
            if isinstance(extra, dict) and extra:
                return {f"key{i}": self._value(extra, f"key{i}", owner, depth + 1) for i in (1, 2)}
            return {}
        obj: dict[str, Any] = {}
        owner_ts = self.models[owner].ts_name if owner in self.models else owner
        for key, prop in props.items():
            override_key = next(
                (k for k in (f"{owner}.{key}".lower(), f"{owner_ts}.{key}".lower(), key.lower()) if k in self.overrides),
                None,
            )
            if override_key is not None:
                obj[key] = copy.deepcopy(self.overrides[override_key])
            elif self._is_long_text(prop, key, owner):
                max_len = _unwrap(prop).get("maxLength")
                obj[key] = self._placeholder(max_len)
                self._seq += 1
                self.slots.append(
                    TextSlot(f"s{self._seq}", owner, key, self._meaning(owner, key, prop), max_len, obj)
                )
            else:
                obj[key] = self._value(prop, key, owner, depth + 1)
        return obj

    # ------------------------------------------------------------------ strings
    def _string(self, schema: dict[str, Any], key: str) -> str:
        if isinstance(schema.get("default"), str):
            return schema["default"]
        fmt = schema.get("format")
        birth = "birth" in _norm(key)  # a date of birth needs an adult age, not a recent date
        value = self._by_format(fmt) if fmt and not birth else None
        if value is None:
            value = self._by_name(_norm(key), key)
        pattern = schema.get("pattern")
        if pattern and not re.search(pattern, value):
            # e.g. Decimal fields serialized as numeric strings.
            numeric = str(self._number({}, key, is_int=False))
            if re.search(pattern, numeric):
                value = numeric
        return self._fit(value, schema.get("minLength"), schema.get("maxLength"))

    def _by_format(self, fmt: str) -> str | None:
        rng = self.rng
        if fmt == "date":
            return (date.today() - timedelta(days=rng.randint(0, 1000))).isoformat()
        if fmt == "date-time":
            moment = datetime.now(UTC) - timedelta(minutes=rng.randint(0, 1_000_000))
            return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        if fmt == "time":
            return f"{rng.randint(6, 21):02d}:{rng.choice([0, 15, 30, 45]):02d}:00"
        if fmt == "email":
            return self._email()
        if fmt == "uuid":
            return str(uuid.UUID(int=rng.getrandbits(128), version=4))
        if fmt in ("uri", "url"):
            return f"https://example.com/{rng.choice(_WORDS)}/{rng.randint(1, 999)}"
        if fmt == "ipv4":
            return ".".join(str(rng.randint(1, 254)) for _ in range(4))
        return None

    def _by_name(self, k: str, raw_key: str) -> str:
        rng = self.rng
        digits = lambda n: "".join(rng.choice(string.digits) for _ in range(n))  # noqa: E731
        if "email" in k:
            return self._email()
        if any(x in k for x in ("phone", "hotline", "mobile")):
            return rng.choice(["09", "03", "07", "08"]) + digits(8)
        if "nationalid" in k or "cccd" in k:
            return rng.choice(["001", "079", "048", "031"]) + digits(9)
        if k == "vin" or k.endswith("vin"):
            return "".join(rng.choice(_VIN_CHARS) for _ in range(17))
        if "plate" in k:
            return f"{rng.randint(11, 99)}{rng.choice('ABCDEFGH')}-{digits(5)}"
        if k.endswith(("fullname", "displayname", "ownername", "managername", "customername")):
            return self._person()
        if "address" in k:
            if self.faker:
                return self.faker.address().replace("\n", ", ")
            return f"{rng.randint(1, 300)} {rng.choice(_STREETS)}, {rng.choice(_WARDS)}, {rng.choice(_DISTRICTS)}, {rng.choice(_PROVINCES)}"
        if k == "ward":
            return rng.choice(_WARDS)
        if k == "district":
            return rng.choice(_DISTRICTS)
        if k in ("province", "city", "region"):
            return self.faker.city() if self.faker else rng.choice(_PROVINCES)
        if any(x in k for x in ("url", "avatar", "image", "link")):
            return f"https://picsum.photos/seed/{rng.randint(1, 9999)}/200"
        if "color" in k:
            return self.faker.color_name() if self.faker else rng.choice(_COLORS)
        if k.endswith("time"):
            return f"{rng.randint(6, 21):02d}:{rng.choice([0, 30]):02d}"
        if "birth" in k or k == "dob":
            return (date.today() - timedelta(days=rng.randint(18 * 365, 65 * 365))).isoformat()
        if k.endswith("date"):
            return (date.today() - timedelta(days=rng.randint(0, 1000))).isoformat()
        if "version" in k:
            return f"{rng.randint(2024, 2026)}-{rng.randint(1, 12):02d}"
        if "token" in k or "hash" in k:
            return "".join(rng.choice("0123456789abcdef") for _ in range(32))
        if k.endswith(("id", "code")):
            prefix = re.sub(r"(_?id|_?code)$", "", raw_key, flags=re.I)
            prefix = re.sub(r"[^A-Za-z]", "", prefix)[:3].upper() or "ID"
            return f"{prefix}-{rng.randint(1, 9999):04d}"
        if k == "name" or k.endswith("name"):
            return " ".join(w.capitalize() for w in rng.sample(_WORDS, 2))
        if "status" in k:
            return rng.choice(["ACTIVE", "PENDING", "INACTIVE"])
        return " ".join(rng.sample(_WORDS, rng.randint(2, 4)))

    def _person(self) -> str:
        if self.faker:
            return self.faker.name()
        return f"{self.rng.choice(_LAST)} {self.rng.choice(_MIDDLE)} {self.rng.choice(_FIRST)}"

    def _email(self) -> str:
        local = re.sub(r"[^a-z]", "", self._person().lower().split()[-1]) or "user"
        return f"{local}.{self.rng.randint(1, 9999)}@example.com"

    def _fit(self, value: str, min_len: int | None, max_len: int | None) -> str:
        if max_len is not None and len(value) > max_len:
            value = value[:max_len].rstrip() or value[:max_len]
        if min_len is not None and len(value) < min_len:
            value += "".join(self.rng.choice(string.ascii_lowercase) for _ in range(min_len - len(value)))
        return value

    # ------------------------------------------------------------------ numbers
    def _number(self, schema: dict[str, Any], key: str, is_int: bool) -> int | float:
        low, high = schema.get("minimum"), schema.get("maximum")
        if isinstance(schema.get("exclusiveMinimum"), (int, float)):
            low = schema["exclusiveMinimum"] + (1 if is_int else 0.01)
        if isinstance(schema.get("exclusiveMaximum"), (int, float)):
            high = schema["exclusiveMaximum"] - (1 if is_int else 0.01)
        decimals: int | None = None if is_int else 2
        hint = next((h for h in _NUMBER_HINTS if h[0] in _norm(key)), None)
        if hint:
            # Narrow to the realistic range, but never leave the schema bounds.
            h_low, h_high = hint[1]
            if not is_int and hint[2] is not None:
                decimals = hint[2]
            new_low = max(low, h_low) if low is not None else h_low
            new_high = min(high, h_high) if high is not None else h_high
            if new_low <= new_high:
                low, high = new_low, new_high
        if low is None and high is None:
            low, high = (0, 100) if is_int else (0, 1000)
        elif low is None:
            low = min(0, high)
        elif high is None:
            high = low + 100
        if is_int:
            return self.rng.randint(int(low), int(high))
        return round(self.rng.uniform(low, high), decimals if decimals is not None else 2)

    # ------------------------------------------------------------------ long text
    def _is_long_text(self, prop: Any, key: str, owner: str) -> bool:
        if not isinstance(prop, dict):
            return False
        schema = _unwrap(prop)
        if schema.get("type") != "string" or any(k in schema for k in ("enum", "const", "format", "examples")):
            return False
        owner_ts = self.models[owner].ts_name if owner in self.models else owner
        if {key.lower(), f"{owner}.{key}".lower(), f"{owner_ts}.{key}".lower()} & self.llm_fields:
            return True
        if not self.auto_long_text or STRUCTURED_NAME_RE.search(_norm(key)):
            return False
        max_len = schema.get("maxLength")
        return (max_len or 0) >= LONG_TEXT_MIN_LENGTH or (max_len is None and bool(LONG_TEXT_NAME_RE.search(key)))

    def _meaning(self, owner: str, key: str, prop: dict[str, Any]) -> str:
        owner_ts = self.models[owner].ts_name if owner in self.models else owner
        for hint_key in (f"{owner}.{key}", f"{owner_ts}.{key}", key):
            if hint_key in self.hints:
                return self.hints[hint_key]
        schema = _unwrap(prop)
        text = schema.get("description") or schema.get("title")
        return text or f"(no description) infer from the field name '{key}' and the record"

    def _placeholder(self, max_len: int | None) -> str:
        words = [self.rng.choice(_WORDS) for _ in range(self.rng.randint(12, 24))]
        text = " ".join(words).capitalize() + "."
        return text[:max_len] if max_len else text

    def _model_context(self, owner: str) -> dict[str, Any]:
        model = self.models.get(owner)
        if model is None:
            return {"model": owner}
        about = self.hints.get(owner) or self.hints.get(model.ts_name) or model.description
        used_by = sorted(
            {f"{k} ({role}) — {self.endpoint_summaries.get(k, '')}".rstrip(" —") for k, role in model.used_by}
        )
        return {"model": model.ts_name, "about": about or "", "usedBy": used_by}

    def fill_with_llm(
        self, config: LLMConfig, language: str = "vi", log: Callable[[str], None] = print
    ) -> int:
        """Replace slot placeholders with LLM text. Returns the number of slots filled."""
        slot_fields: dict[int, set[str]] = {}
        for slot in self.slots:
            slot_fields.setdefault(id(slot.target), set()).add(slot.field)

        filled = 0
        for start in range(0, len(self.slots), LLM_BATCH_SIZE):
            chunk = self.slots[start : start + LLM_BATCH_SIZE]
            owners = sorted({s.owner for s in chunk})
            payload = []
            for s in chunk:
                record = {k: v for k, v in s.target.items() if k not in slot_fields[id(s.target)]}
                record_json = json.dumps(record, ensure_ascii=False, default=str)
                payload.append(
                    {
                        "id": s.id,
                        "model": self.models[s.owner].ts_name if s.owner in self.models else s.owner,
                        "field": s.field,
                        "meaning": s.meaning,
                        "maxLength": s.max_length,
                        # Keep the prompt small: very large records are cut as text.
                        "record": record if len(record_json) <= 1500 else record_json[:1500],
                    }
                )
            prompt = _PROMPT.format(
                language=_LANGUAGES.get(language, language),
                models=json.dumps([self._model_context(o) for o in owners], ensure_ascii=False, indent=2),
                slots=json.dumps(payload, ensure_ascii=False, indent=2),
            )
            try:
                result = complete_json(config, _SYSTEM, prompt)
            except (LLMError, ValueError, KeyError) as exc:
                log(f"warning: LLM batch {start // LLM_BATCH_SIZE + 1} failed, placeholders kept: {exc}")
                continue
            for s in chunk:
                text = result.get(s.id)
                if isinstance(text, str) and text.strip():
                    s.target[s.field] = text.strip()[: s.max_length] if s.max_length else text.strip()
                    filled += 1
        return filled


_SYSTEM = "You write realistic, domain-appropriate sample text for API test data. Reply with one JSON object only."

_PROMPT = """Write the text for every slot below.
Language: {language}.

Rules:
- Follow the field "meaning" and the model's purpose ("about", "usedBy").
- Stay consistent with the slot's "record" (the other fields of the same object).
- Respect "maxLength" when it is set. Vary wording between slots; never repeat a sentence.
- Plain text only, no markdown.

Return a JSON object mapping every slot id to its text: {{"s1": "...", "s2": "..."}}

Models:
{models}

Slots:
{slots}
"""
