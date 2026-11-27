"""Conservative extraction for plain-text billing notices."""
from datetime import date, datetime
import os
import re

from babel.core import get_global
from babel.numbers import get_currency_precision

CURRENCIES = get_global("all_currencies")
MONEY = re.compile(r"\b([A-Z]{3})\s+(\d+(?:,\d{3})*(?:\.\d+)?)(?!\d|[.,]\d)|(?<![\d.,-])(\d+(?:,\d{3})*(?:\.\d+)?)\s+([A-Z]{3})\b")
MONTH_NAMES = "January February March April May June July August September October November December".split()
MONTH_NUMBER = {name[:3].lower(): number for number, name in enumerate(MONTH_NAMES, 1)}
MONTH = "(?:" + "|".join(f"{name[:3]}(?:{name[3:]})?" if len(name) > 3 else name for name in MONTH_NAMES) + "|Sept)"
DATE_PATTERN = re.compile(
    rf"\b(?:(?P<iso>\d{{4}}-\d{{2}}-\d{{2}})|(?P<numeric>\d{{1,2}}/\d{{1,2}}/\d{{4}})"
    rf"|(?P<month_first>{MONTH})\.?\s+(?P<day_after>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<year_after>\d{{4}})"
    rf"|(?P<day_before>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month_after>{MONTH})\.?,?\s+(?P<year_before>\d{{4}}))\b",
    re.I,
)
REFERENCE = re.compile(r"\b(?:receipt|(?:transaction|payment|merchant)\s+(?:reference|ref|id)|ref)\s*[:#]?\s*([A-Z0-9]+(?:-[A-Z0-9]+)*)\b", re.I)
CYCLE = re.compile(r"\b(monthly|annual(?:ly)?|yearly)\b", re.I)
FAKE_INSTRUCTION = re.compile(r"\b(?:ignore (?:all|previous|your|the)|pretend|instead output|assistant:|system:|mark .{0,40} as paid)\b", re.I)
CONFIRMED = re.compile(r"\b(?:auto[- ]renew(?:al)?\s+(?:is\s+|has been\s+)?(?:off|disabled|turned off)|will not be (?:billed|charged)|subscription (?:has been |is )?cancelled|subscription (?:has been |is )?canceled)\b", re.I)
REQUESTED = re.compile(r"\b(?:cancellation request|request to cancel|request was received)\b", re.I)
FAILED = re.compile(r"\b(?:failed|declined|unsuccessful|unpaid|not (?:yet )?(?:paid|collected|charged))\b", re.I)
PAYMENT = re.compile(r"\b(?:paid(?!\s+plan)|payment (?:was |has been )?(?:received|collected|confirmed|successful)|(?:successfully|already) charged|charged successfully|duplicate confirmation of .*?payment)\b", re.I)
SUSPENDED = re.compile(r"\b(?:subscription|membership|plan)\b[^.!?\n]{0,55}\b(?:suspended|paused)\b", re.I)
TRIAL = re.compile(r"\b(?:trial .{0,60}(?:convert|transition|become|ends?)|(?:first charge|trial conversion))", re.I)
RENEWAL = re.compile(r"\b(?:renewal|renews? on|will (?:auto[- ]|automatically )?renew|next charge|scheduled (?:charge|payment)|will be (?:charged|billed))\b", re.I)
PROMO = re.compile(r"\b(?:promotional|special offer|discount(?:ed|s)?|sale|shop now|offer ends|limited[- ]time)\b", re.I)
MARKETING_CTA = re.compile(r"\b(?:shop|upgrade|subscribe|buy|save|sign up|offer|if you)\b", re.I)
CONDITIONAL_SIGNUP = re.compile(r"\b(?:if|when|once) you (?:subscribe|sign up|upgrade|buy|purchase)\b", re.I)
SCHEDULED_RENEWAL = re.compile(r"\b(?:scheduled|will (?:renew|be charged|be billed)|renews? on|next charge)\b", re.I)
RECURRING = re.compile(
    r"\b(?:auto[- ]?renew(?:s|al)?|recurring (?:charge|payment|billing)|"
    r"(?:monthly|annual|yearly) (?:subscription|membership|billing)|"
    r"(?:subscription|membership)\s+(?:renews?|payment|receipt|billed|suspended|paused|cancellation|will (?:automatically )?renew)|"
    r"(?:your (?:[\w-]+ ){0,5}(?:subscription|membership))|"
    r"(?:\d+ (?:months?|years?) (?:subscription|membership)))\b|"
    r"\b(?:subscription|membership)\s*(?:[:(]|[.!?]?\s*$)", re.I | re.M,
)
ORDER = re.compile(
    r"\b(?:order (?:confirmation|(?:is |being )?processed|(?:is )?confirmed|shipped|delivered)|"
    r"order\s+#?\d+\s+(?:confirmation|confirmed)|shipping (?:address|confirmation))\b", re.I,
)
ONE_TIME = re.compile(r"\b(?:one[- ]time purchase|purchase type\s*:\s*one[- ]time)\b", re.I)
EDITORIAL = re.compile(r"^(?:\s*(?:newsletter|digest)\b|\s*what\b.+\bmeans for\b)", re.I)
RECEIPT_SUBJECT = re.compile(r"\b(?:your .{0,30}order receipt|order (?:receipt|confirmation)|deserves a receipt|payment deduction)\b", re.I)
PRODUCT_LINE = re.compile(r"^\s*(?:subscription|membership|plan|item|product)\s*:\s*(.+)$", re.I | re.M)
NAMED_NOTICE = re.compile(
    r"^(?:your\s+trial for\s+(.+?)(?:\s+(?:will|ends?)\b|$)|"
    r"(?:payment (?:failed|declined)|(?:failed|declined) payment) for\s+(.+?)(?:\s+(?:subscription|membership)\b|$))",
    re.I,
)
TRIAL_CHARGE = re.compile(r"\b(?:convert\w*|transition\w*|become\w*|first charge|will be (?:charged|billed))\b", re.I)

PLAN_PREFIX = re.compile(
    r"^(?:duplicate confirmation of (?:the same )?|(?:payment received|receipt|renewal notice|payment update|"
    r"subscription update|cancellation confirmation)\s*[:–-]\s*|your\s+)", re.I,
)
PLAN_END = re.compile(
    r"\s+(?:upcoming\s+)?(?:monthly|annual|yearly|subscription|payment|receipt|renewal|auto[- ]renew(?:al)?|"
    r"converts?|has converted|will|was|has been|is|paid|on)\b|[,.:]", re.I,
)
PLAN_IN_BODY = re.compile(
    r"\s+(?:(?:monthly|annual|yearly)\s+(?:subscription|renewal)|payment|auto[- ]renew(?:al)?|converts?)\b",
    re.I,
)


def _money(text):
    amounts = set()
    for match in MONEY.finditer(text):
        first, number, other_number, last = match.groups()
        currency = first or last
        if currency not in CURRENCIES:
            continue
        whole, _, fraction = (number or other_number).replace(",", "").partition(".")
        precision = get_currency_precision(currency)
        if len(fraction.rstrip("0")) > precision or len(whole) > 15:
            amounts.add((currency, None))
            continue
        minor = int(whole) * 10**precision + int((fraction[:precision].ljust(precision, "0") or "0"))
        amounts.add((currency, minor))
    if len(amounts) == 1:
        return amounts.pop()
    currencies = {currency for currency, _ in amounts}
    return (currencies.pop(), None) if len(currencies) == 1 else (None, None)


def _stated_date(text):
    dates = set()
    for match in DATE_PATTERN.finditer(text):
        if match["iso"]:
            parts = [tuple(map(int, match["iso"].split("-")))]
        elif match["numeric"]:
            first, second, year = map(int, match["numeric"].split("/"))
            # When both orders are valid and differ, the message is ambiguous.
            parts = [(year, second, first), (year, first, second)]
        else:
            month = MONTH_NUMBER[(match["month_first"] or match["month_after"])[:3].lower()]
            day = int(match["day_after"] or match["day_before"])
            year = int(match["year_after"] or match["year_before"])
            parts = [(year, month, day)]
        for year, month, day in parts:
            try:
                dates.add(date(year, month, day).isoformat())
            except ValueError:
                continue
    return dates.pop() if len(dates) == 1 else None


def _subscription(message, body):
    raw_subject = message["subject"].strip()
    subject = PLAN_PREFIX.sub("", raw_subject)
    first_line = PLAN_PREFIX.sub("", body.splitlines()[0].strip())
    # Receipts and renewal notices can put references or qualifiers in the
    # subject. A recognizable plan phrase in the billing text is more stable.
    product = PRODUCT_LINE.search(body)
    named = NAMED_NOTICE.search(raw_subject)
    candidates = []
    if product:
        candidates.append(re.split(r"\s+\(", product[1], maxsplit=1)[0])
    if named:
        candidates.append(named[1] or named[2])
    if PLAN_IN_BODY.search(first_line):
        candidates.append(first_line)
    if not RECEIPT_SUBJECT.search(raw_subject) and not ORDER.search(raw_subject):
        candidates.append(subject)
    for candidate in candidates:
        name = PLAN_END.split(candidate, maxsplit=1)[0].strip()
        if (
            name
            and len(name.split()) <= 7
            and re.fullmatch(r"[\w &+'-]+", name)
            and not re.match(
                r"^(?:on|paid|charge|payment|receipt|failed|promo|renewal|cancellation|trial|notice|billing|"
                r"subscription|membership|monthly|annual|yearly|we|you)\b", name, re.I
            )
        ):
            return re.sub(r"[^\w]+", "-", name.casefold()).strip("-")
    domain = message["sender_domain"].lower().rstrip(".")
    if domain == "grammarly.com" or domain.endswith(".grammarly.com"):
        return "grammarly"
    # Generic processor receipts need separate identities until the actual plan is known.
    source = re.sub(r"[^\w-]+", "-", message["source_id"]).strip("-")
    return "receipt-" + source


def _classify(clause):
    if CONDITIONAL_SIGNUP.search(clause):
        return "promo"
    if PROMO.search(clause):
        billing_fact = (
            PAYMENT.search(clause) or CONFIRMED.search(clause) or FAILED.search(clause)
            or (SCHEDULED_RENEWAL.search(clause) and _stated_date(clause))
        )
        if not billing_fact or MARKETING_CTA.search(clause):
            return "promo"
    for pattern, kind in (
        (REQUESTED, "cancellation_requested"),
        (CONFIRMED, "cancellation_confirmed"),
        (SUSPENDED, "suspended"),
        (FAILED, "failed"),
        (TRIAL, "trial_conversion"),
        (PAYMENT, "payment"),
        (RENEWAL, "renewal"),
    ):
        if pattern.search(clause):
            return kind
    return None


def _subscription_basis(subject, contents, kinds):
    if ONE_TIME.search(contents):
        return "one_time"
    clauses = re.split(r"(?<=[.!?])\s+|[\r\n;]+", contents)
    recurring = any(RECURRING.search(clause) and _classify(clause) != "promo" for clause in clauses)
    if ORDER.search(contents) and not recurring:
        return "one_time"
    if recurring or kinds & {"trial_conversion", "cancellation_confirmed", "suspended"}:
        return "subscription"
    if "renewal" in kinds and not RECEIPT_SUBJECT.search(subject):
        return "subscription"
    return "uncertain"


def _segments(text):
    text = re.sub(rf"\b({MONTH})\.(?=\s+\d)", r"\1", text, flags=re.I)
    clauses = re.split(r"(?<=[.!?])\s+|[\r\n;]+|,\s+(?:and\s+)?(?=(?:your\s+)?(?:next charge|renewal|will be charged)\b)", text, flags=re.I)
    grouped = []
    for clause in clauses:
        kind = _classify(clause)
        same_notice = grouped and kind == grouped[-1][0] and (
            kind in {"trial_conversion", "cancellation_confirmed"} or (
                kind == "payment" and not MONEY.search(" ".join(grouped[-1][1]))
                and MONEY.search(clause)
            )
        )
        if grouped and (not kind or same_notice):
            grouped[-1][1].append(clause)
        elif kind:
            grouped.append((kind, [clause]))
    return [(kind, " ".join(parts)) for kind, parts in grouped]


def _reference(text):
    for match in REFERENCE.findall(text):
        if any(char.isdigit() for char in match):
            return match.upper()
    shorthand = re.findall(r"\b[A-Z]{1,8}-\d+\b", text)
    return shorthand[0] if len(set(shorthand)) == 1 else None


def extract_events(messages, *, gemini_fallback=None):
    """Extract billing evidence, optionally filling gaps from Gemini-selected excerpts."""
    if gemini_fallback is None:
        gemini_fallback = os.getenv("SUBGUARD_GEMINI_EXTRACTION", "").strip().lower() in {"1", "true"}
    events = {}
    fallback_evidence = {}
    for message in messages:
        subject, body = message["subject"], message["body_text"]
        contents = "\n".join((subject, body)).strip()
        if not contents or EDITORIAL.search(subject) or FAKE_INSTRUCTION.search(contents):
            continue
        segments = [
            (kind, evidence) for kind, evidence in (_segments(body) or _segments(contents))
            if kind != "promo"
        ]
        kinds = {kind for kind, _ in segments}
        subject_kind = _classify(subject)
        if subject_kind in {"suspended", "trial_conversion", "failed", "cancellation_confirmed"} and subject_kind not in kinds:
            segments.insert(0, (subject_kind, subject))
            kinds.add(subject_kind)
        basis = _subscription_basis(subject, contents, kinds)
        if basis == "one_time":
            continue
        key = _subscription(message, body.strip() or contents)
        seen = set()
        recurring = re.search(
            r"\b(?:(?:auto[- ]?renews?|renews?)\s+(?:monthly|annually|yearly)|"
            r"(?:monthly|annual|yearly)\s+(?:subscription|billing))\b", contents, re.I,
        )
        for kind, evidence in segments:
            currency, amount = _money(evidence)
            stated = _stated_date(evidence)
            cycle_match = CYCLE.search(evidence) or CYCLE.search(message["subject"])
            if not cycle_match and kind == "payment" and recurring:
                cycle_match = CYCLE.search(recurring[0])
            cycle = None if not cycle_match else ("monthly" if cycle_match[0].lower() == "monthly" else "annual")
            if kind == "payment" and not stated:
                stated = datetime.fromisoformat(message["received_at"].replace("Z", "+00:00")).date().isoformat()
            next_date = stated if kind in {"renewal", "trial_conversion"} else None
            if kind == "trial_conversion" and not TRIAL_CHARGE.search(evidence):
                next_date = None
            ref = _reference(evidence)
            identity = (kind, currency, amount, ref, stated)
            if identity in seen:
                continue
            source = message["source_id"]
            event_id = f"{source}:{len(seen)}"
            seen.add(identity)
            events[event_id] = {
                "event_id": event_id,
                "source_id": source,
                "received_at": message["received_at"],
                "subscription_key": key,
                "kind": kind,
                "currency": currency,
                "amount_minor": amount,
                "cycle": cycle,
                "transaction_ref": ref,
                "event_date": stated if kind in {"payment", "failed"} else None,
                "effective_date": stated if kind == "cancellation_confirmed" else None,
                "next_charge_date": next_date,
                "date_basis": "confirmed" if next_date else "unknown",
            }
            if basis == "uncertain":
                events[event_id]["subscription_basis"] = "uncertain"
            if (
                gemini_fallback and len(segments) == 1 and kind in {"payment", "renewal", "trial_conversion"}
                and (cycle is None or amount is None)
            ):
                fallback_evidence[event_id] = contents

    if fallback_evidence:
        from .extraction_fallback import fill_missing_fields
        fill_missing_fields(events, fallback_evidence, _money)
    return list(events.values())
