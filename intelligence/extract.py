"""Conservative extraction for plain-text billing notices."""
from datetime import date, datetime
import re

from babel.core import get_global
from babel.numbers import get_currency_precision

CURRENCIES = get_global("all_currencies")
MONEY = re.compile(r"\b([A-Z]{3})\s+(\d+(?:,\d{3})*(?:\.\d+)?)(?!\d|[.,]\d)|(?<![\d.,-])(\d+(?:,\d{3})*(?:\.\d+)?)\s+([A-Z]{3})\b")
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
REFERENCE = re.compile(r"\b(?:receipt|(?:transaction|payment|merchant)\s+(?:reference|ref|id)|ref)\s*[:#]?\s*([A-Z0-9]+(?:-[A-Z0-9]+)*)\b", re.I)
CYCLE = re.compile(r"\b(monthly|annually?|yearly)\b", re.I)
FAKE_INSTRUCTION = re.compile(r"\b(?:ignore (?:all|previous|your|the)|pretend|instead output|assistant:|system:|mark .{0,40} as paid)\b", re.I)
CONFIRMED = re.compile(r"\b(?:auto[- ]renew(?:al)?\s+(?:is\s+|has been\s+)?(?:off|disabled|turned off)|will not be (?:billed|charged)|subscription (?:has been |is )?cancelled|subscription (?:has been |is )?canceled)\b", re.I)
REQUESTED = re.compile(r"\b(?:cancellation request|request to cancel|request was received)\b", re.I)
FAILED = re.compile(r"\b(?:failed|declined|unsuccessful|unpaid|not (?:yet )?(?:paid|collected|charged))\b", re.I)
PAYMENT = re.compile(r"\b(?:paid(?!\s+plan)|payment (?:was |has been )?(?:received|collected|confirmed|successful)|(?:successfully|already) charged|charged successfully|duplicate confirmation of .*?payment)\b", re.I)
TRIAL = re.compile(r"\b(?:trial .{0,60}(?:convert|transition|become|ends?)|(?:first charge|trial conversion))", re.I)
RENEWAL = re.compile(r"\b(?:renewal|renews? on|will (?:auto[- ])?renew|next charge|scheduled (?:charge|payment)|will be (?:charged|billed))\b", re.I)
PROMO = re.compile(r"\b(?:promotional|special offer|discount|sale)\b", re.I)

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
    for match in ISO_DATE.findall(text):
        try:
            dates.add(date.fromisoformat(match).isoformat())
        except ValueError:
            continue
    return dates.pop() if len(dates) == 1 else None


def _subscription(message, body):
    subject = PLAN_PREFIX.sub("", message["subject"].strip())
    first_line = PLAN_PREFIX.sub("", body.splitlines()[0].strip())
    # Receipts and renewal notices can put references or qualifiers in the
    # subject. A recognizable plan phrase in the billing text is more stable.
    candidates = (first_line, subject) if PLAN_IN_BODY.search(first_line) else (subject,)
    for candidate in candidates:
        name = PLAN_END.split(candidate, maxsplit=1)[0].strip()
        if (
            name
            and len(name.split()) <= 7
            and re.fullmatch(r"[\w &+'-]+", name)
            and not re.match(r"^(?:on|paid|charge|payment|receipt|failed|promo|renewal|cancellation|trial|notice|billing|we|you)\b", name, re.I)
        ):
            return re.sub(r"[^\w]+", "-", name.casefold()).strip("-")
    return "merchant-" + re.sub(r"[^a-z0-9]+", "-", message["sender_domain"].lower()).strip("-")


def _classify(clause):
    for pattern, kind in (
        (REQUESTED, "cancellation_requested"),
        (CONFIRMED, "cancellation_confirmed"),
        (FAILED, "failed"),
        (PROMO, "promo"),
        (TRIAL, "trial_conversion"),
        (PAYMENT, "payment"),
        (RENEWAL, "renewal"),
    ):
        if pattern.search(clause):
            # A decline or promo is classified above any apparent payment.
            return kind
    return None


def _segments(text):
    clauses = re.split(r"(?<=[.!?])\s+|[\r\n;]+|,\s+(?:and\s+)?(?=(?:your\s+)?(?:next charge|renewal|will be charged)\b)", text, flags=re.I)
    grouped = []
    for clause in clauses:
        kind = _classify(clause)
        if grouped and (not kind or kind == grouped[-1][0] and kind in {"trial_conversion", "cancellation_confirmed"}):
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


def extract_events(messages):
    """Extract explicit billing evidence from sanitized Message dictionaries."""
    events = {}
    for message in messages:
        contents = "\n".join((message["subject"], message["body_text"])).strip()
        if not contents or FAKE_INSTRUCTION.search(contents):
            continue
        key = _subscription(message, message["body_text"].strip() or contents)
        seen = set()
        segments = _segments(message["body_text"]) or _segments(contents)
        recurring = re.search(r"\b(?:auto[- ]?renews?|renews?)\s+(?:monthly|annually|yearly)\b", contents, re.I)
        for kind, evidence in segments:
            currency, amount = _money(evidence)
            stated = _stated_date(evidence)
            cycle_match = CYCLE.search(evidence) or CYCLE.search(message["subject"])
            if not cycle_match and kind == "payment" and recurring:
                cycle_match = CYCLE.search(recurring[0])
            cycle = None if not cycle_match else ("monthly" if cycle_match[0].lower() == "monthly" else "annual")
            if kind == "payment" and not stated and re.search(r"\btoday\b", evidence, re.I):
                stated = datetime.fromisoformat(message["received_at"].replace("Z", "+00:00")).date().isoformat()
            next_date = stated if kind in {"renewal", "trial_conversion"} else None
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
    return list(events.values())
