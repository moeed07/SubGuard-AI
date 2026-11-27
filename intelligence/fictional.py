"""Shared fictional messages at the guide's fixed demo clock."""
AS_OF = "2026-11-26"
TIMEZONE = "Asia/Karachi"

_NOTICES = (
    ("Writing Plus", "Writing Plus monthly subscription. Paid PKR 2,000 today. Receipt W-101. Auto-renews monthly."),
    ("Writing Plus", "Duplicate confirmation of the same Writing Plus payment, W-101, PKR 2,000."),
    ("Design Pro", "Design Pro annual subscription. Paid PKR 12,000. Receipt D-201. Auto-renews annually."),
    ("Design Pro", "Design Pro annual renewal of PKR 12,000 is scheduled on 2026-12-01."),
    ("Sketch Trial", "Sketch Trial converts to a paid plan on 2026-11-29. First charge PKR 700."),
    ("Example Promo", "Promotional offer for a new plan, PKR 500."),
    ("Example Debit", "Failed debit of PKR 3,000."),
    ("Design Pro", "Design Pro auto-renewal is OFF. Your access ends 2026-12-01. You will not be billed on 2026-12-01."),
)


def fictional_messages(*, canceled=False):
    return [
        {
            "source_id": f"m{index}",
            "received_at": f"{AS_OF}T{index + 7:02}:00:00Z",
            "sender_domain": "billing.example",
            "subject": subject,
            "body_text": body,
        }
        for index, (subject, body) in enumerate(_NOTICES if canceled else _NOTICES[:-1], 1)
    ]
