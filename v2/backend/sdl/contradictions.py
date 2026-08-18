"""Facts the corpus states more than once, differently.

A store where everything agrees tests insertion. What a user actually has is a
chat message saying the review is on Thursday, a calendar entry saying Friday,
and an email confirming the move — and the only useful answer is Friday, with
the Thursday message still findable when they ask what they were told at the
time.

`world.disputes` decides what is disputed and what the right answer is. This
module writes the ARTIFACTS that carry each claim, so the conflict exists in the
corpus rather than only in the answer key. A benchmark whose contradictions live
only in ground truth is asking a system to reproduce a file it cannot read.

The resolution rule, stated once here so it cannot drift from the data:

    authority first, then recency inside the winning tier.

A calendar is the system of record for when something happens; an email is a
deliberate statement; a chat message is somebody's recollection. Both halves of
the rule are exercised, because a rule only ever tested one way is a rule nobody
has tested: half the disputes put the LATER claim in the weaker source, so a
system resolving purely by recency gets them wrong, and half put two claims of
equal standing months apart, so a system resolving purely by authority cannot
separate them.
"""
from __future__ import annotations

from .world import AUTHORITY, World

# What each claim looks like when it is written down as an artifact.
PHRASING = {
    "meeting_day": "{about} is on {value}",
    "location": "{about} is in {value}",
    "deadline": "the deadline for {about} is {value}",
}

BY_KIND = {
    "chat": "recalled in a message",
    "email": "stated in an email",
    "calendar": "recorded in the calendar",
}


def build(world: World) -> dict:
    """Artifacts carrying every claim, and the answer key for each dispute."""
    claims: list[dict] = []
    resolutions: list[dict] = []

    for dispute in world.disputes:
        about = dispute.about or dispute.question.rstrip("?")
        template = PHRASING.get(dispute.topic, "{about}: {value}")
        winner = dispute.resolved

        for claim in dispute.claims:
            text = template.format(about=about, value=claim["value"])
            claims.append({
                "id": claim["source_id"],
                "dispute": dispute.id,
                "topic": dispute.topic,
                "source_kind": claim["source_kind"],
                "authority": claim["authority"],
                "month": claim["month"],
                "date": world.month_date(claim["month"]).isoformat(),
                "value": claim["value"],
                "text": f"{text} ({BY_KIND[claim['source_kind']]})",
                # Marked on the artifact as well as in ground truth. A system
                # under test never reads this field — it exists so a human
                # debugging a wrong answer can see which row should have won
                # without cross-referencing two files.
                "authoritative": claim["source_id"] == winner["source_id"],
            })

        resolutions.append({
            "dispute": dispute.id,
            "topic": dispute.topic,
            "question": dispute.question,
            "answer": winner["value"],
            "decided_by": winner["source_kind"],
            "decided_at_month": winner["month"],
            "winning_source": winner["source_id"],
            "superseded": sorted(c["source_id"] for c in dispute.claims
                                 if c["source_id"] != winner["source_id"]),
            # Which half of the rule this dispute exercises, so a report can say
            # "every authority case passed and every recency case failed"
            # instead of "eleven contradictions were wrong".
            "tests": ("authority"
                      if len({c["authority"] for c in dispute.claims}) > 1
                      else "recency"),
        })

    return {"claims": claims, "resolutions": resolutions}


def resolve(claims: list[dict]) -> dict | None:
    """The rule itself, applied to a set of claims about one fact.

    Exposed so a caller can check the answer key against the rule rather than
    trusting that the two were written to agree.
    """
    if not claims:
        return None
    return max(claims, key=lambda c: (c["authority"], c["month"]))


def rule_holds(world: World) -> bool:
    """Every dispute's recorded answer matches what the rule produces."""
    for dispute in world.disputes:
        expected = resolve([{**c, "authority": AUTHORITY[c["source_kind"]]}
                            for c in dispute.claims])
        if expected["value"] != dispute.resolved["value"]:
            return False
    return True
