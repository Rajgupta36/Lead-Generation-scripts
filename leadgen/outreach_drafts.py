from __future__ import annotations

import re
from dataclasses import dataclass


AGENCY_NAME = "NexStudio"
AGENCY_URL = "nexstudio.work"


@dataclass(frozen=True)
class Draft:
    key: str
    label: str
    subject: str
    body: str


def generate_drafts(lead: dict[str, str], audit: dict[str, str]) -> list[Draft]:
    if not audit_is_sendable(audit) or not lead_is_sendable(lead, audit):
        return []

    company = lead.get("business_name", "").strip() or "your business"
    name = lead.get("name", "").strip()
    first_name = name.split()[0] if name else ""
    greeting = f"Hi {first_name}," if first_name else f"Hi {company} team,"
    subject_name = first_name or company
    segment = lead.get("segment", "").strip()
    observation = sentence(audit.get("specific_observation", ""))
    reason = sentence(audit.get("business_reason", ""))
    show_on_call = clean_phrase(audit.get("what_to_show_on_call", ""))
    scope = offer_scope(audit.get("recommended_offer", ""))
    outcome = commercial_outcome(segment)
    signature = f"{AGENCY_NAME}\n{AGENCY_URL}"

    return [
        Draft(
            key="direct_finding",
            label="Direct finding",
            subject=f"{subject_name}, one issue on {possessive(company)} site",
            body=(
                f"{greeting}\n\n"
                f"I reviewed {possessive(company)} website and noticed "
                f"{lower_first(observation)}\n\n"
                f"{reason} We mapped a focused fix: {show_on_call}. This is a defined "
                f"growth build aimed at {outcome}, not a general website redesign.\n\n"
                "I can walk you through the marked-up plan in 15 minutes. Would Tuesday or "
                "Wednesday work better?\n\n"
                f"{signature}"
            ),
        ),
        Draft(
            key="decision_impact",
            label="Decision impact",
            subject=f"A decision-point issue on {possessive(company)} site",
            body=(
                f"{greeting}\n\n"
                f"The reason I flagged {possessive(company)} website is specific: "
                f"{lower_first(observation)}\n\n"
                f"{reason} That is a decision-point problem, so the useful fix is {scope}, "
                "not more traffic sent into the same path.\n\n"
                f"I have {show_on_call} ready to review. Can we use 15 minutes Tuesday or "
                "Wednesday?\n\n"
                f"{signature}"
            ),
        ),
        Draft(
            key="build_scope",
            label="Build scope",
            subject=f"The first build I would make for {company}",
            body=(
                f"{greeting}\n\n"
                f"I mapped the first growth build I would make for {company} after seeing "
                f"{lower_first(observation)}\n\n"
                f"The scope is {scope}. {reason} The commercial goal is {outcome}; everything "
                "outside that path stays out of scope.\n\n"
                f"I can show you {show_on_call} and the implementation order in 15 minutes. "
                "Would Tuesday or Wednesday work?\n\n"
                f"{signature}"
            ),
        ),
        Draft(
            key="commercial_case",
            label="Commercial case",
            subject=f"Why this matters commercially for {company}",
            body=(
                f"{greeting}\n\n"
                f"One point from my review of {company}: {lower_first(observation)}\n\n"
                f"{reason} The business case is straightforward: remove that friction before "
                f"spending more to attract visitors. We would measure the build against "
                f"{outcome}.\n\n"
                f"I can bring {show_on_call} and review it with you in 15 minutes. Is Tuesday "
                "or Wednesday better?\n\n"
                f"{signature}"
            ),
        ),
        Draft(
            key="close_loop",
            label="Close loop",
            subject=f"Close the loop on {possessive(company)} website?",
            body=(
                f"{greeting}\n\n"
                f"I am closing the loop on the website review I prepared for {company}. The "
                f"finding was: {lower_first(observation)}\n\n"
                f"I have {show_on_call} ready. If {outcome} is a current priority, we can "
                "review it and decide whether the economics justify a build.\n\n"
                "Worth 15 minutes Tuesday or Wednesday? If it is not a priority, I will close "
                "the file.\n\n"
                f"{signature}"
            ),
        ),
    ]


def commercial_outcome(segment: str) -> str:
    return {
        "agency_owner": "more qualified discovery calls and better-fit retainers",
        "coach": "more qualified coaching conversations and higher-value engagements",
        "small_business": "more booked appointments for high-value services",
    }.get(segment, "more qualified sales conversations")


def audit_is_sendable(audit: dict[str, str]) -> bool:
    status = audit.get("audit_status", "").strip().lower()
    confidence = audit.get("confidence", "").strip().lower()
    observation = " ".join(audit.get("specific_observation", "").split()).lower()
    blocked_phrases = (
        "could not reliably inspect",
        "needs manual research",
        "did not expose a complete",
    )
    return bool(
        observation
        and status != "research_required"
        and confidence != "low"
        and not any(phrase in observation for phrase in blocked_phrases)
    )


def lead_is_sendable(lead: dict[str, str], audit: dict[str, str]) -> bool:
    if lead.get("segment", "").strip() != "agency_owner":
        return True
    if lead.get("workflow", "").strip() != "agency_partners":
        return False
    evidence = " ".join(
        [
            audit.get("specific_observation", ""),
            audit.get("what_to_show_on_call", ""),
        ]
    ).lower()
    forbidden_services = (
        "web design",
        "website design",
        "web development",
        "website development",
        "seo",
        "search engine optimization",
    )
    return not any(service in evidence for service in forbidden_services)


def offer_scope(offer: str) -> str:
    return {
        "High-Intent Service Page Pack": (
            "a focused service-page build with decision-stage copy, proof, search intent, "
            "and one enquiry path"
        ),
        "Website Conversion Sprint": (
            "a conversion sprint that tightens the offer, proof, and next action around one "
            "measurable journey"
        ),
        "Lead Response Automation Setup": (
            "a lead-response system covering acknowledgement, qualification, reminders, "
            "owner alerts, and booking handoff"
        ),
    }.get(
        offer,
        "a focused acquisition build tied to one measurable sales outcome",
    )


def clean_phrase(value: str) -> str:
    cleaned = " ".join((value or "").split()).strip()
    if not cleaned:
        return "a focused plan for moving more qualified visitors into conversations"
    return re.sub(r"\bI would\b", "we would", cleaned.rstrip(".!?"))


def sentence(value: str) -> str:
    cleaned = " ".join((value or "").split()).strip()
    if not cleaned:
        return "the site has a measurable gap between visitor interest and a qualified conversation."
    return cleaned if cleaned.endswith((".", "!", "?")) else cleaned + "."


def lower_first(value: str) -> str:
    if not value:
        return value
    if value.startswith("I "):
        return value
    return value[:1].lower() + value[1:]


def possessive(value: str) -> str:
    return value + "'" if value.lower().endswith("s") else value + "'s"
