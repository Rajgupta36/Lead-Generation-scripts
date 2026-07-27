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
    raw_page_findings = " ".join((audit.get("page_findings", "") or "").split()).strip()
    page_findings = sentence(clean_phrase(raw_page_findings)) if raw_page_findings else ""
    if raw_page_findings:
        return generate_specific_evidence_drafts(lead, audit, page_findings)
    observation = sentence(audit.get("specific_observation", ""))
    reason = sentence(audit.get("business_reason", ""))
    show_on_call = clean_phrase(audit.get("what_to_show_on_call", ""))
    scope = offer_scope(audit.get("recommended_offer", ""))
    outcome = commercial_outcome(segment)
    signature = f"{AGENCY_NAME}\n{AGENCY_URL}"

    return generate_human_observation_drafts(
        lead,
        audit,
        observation,
        reason,
        show_on_call,
        scope,
        outcome,
        signature,
    )

    return [  # pragma: no cover - retained as documentation for the legacy variants
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


def generate_human_observation_drafts(
    lead: dict[str, str],
    audit: dict[str, str],
    observation: str,
    reason: str,
    show_on_call: str,
    scope: str,
    outcome: str,
    signature: str,
) -> list[Draft]:
    company = lead.get("business_name", "").strip() or "your business"
    name = lead.get("name", "").strip()
    first_name = name.split()[0] if name else ""
    greeting = f"Hi {first_name}," if first_name else f"Hi {company} team,"
    subject_name = first_name or company
    segment = lead.get("segment", "").strip()
    context = buyer_context(segment, observation)
    strength = strength_line(segment)
    funnel = audit.get("funnel_sequence", "").strip() or "the service page into an enquiry decision"

    return [
        Draft(
            key="human_finding",
            label="Direct finding",
            subject=f"{subject_name}, one thing I noticed on your site",
            body=(
                f"{greeting}\n\n"
                f"I reviewed the path a buyer takes from the {company} website to an enquiry.\n\n"
                f"{strength}. I did notice that {lower_first(observation)}\n\n"
                f"{context} The current path is {funnel}. {reason}\n\n"
                f"I mapped a focused fix: {scope}. I can show you {show_on_call} and the proposed path in 15 minutes. Would Tuesday or Wednesday work better?\n\n"
                f"{signature}"
            ),
        ),
        Draft(
            key="human_impact",
            label="Buyer impact",
            subject=f"A buyer-path issue on {possessive(company)} site",
            body=(
                f"{greeting}\n\n"
                f"The reason I flagged {company} is specific: {lower_first(observation)}\n\n"
                f"{context} That is the point where a qualified visitor decides whether to continue. {reason}\n\n"
                f"The useful fix is {scope}, not a general website rebuild. I have {show_on_call} ready to review in 15 minutes. Can we use Tuesday or Wednesday?\n\n"
                f"{signature}"
            ),
        ),
        Draft(
            key="human_scope",
            label="Build scope",
            subject=f"The first conversion fix I would make for {company}",
            body=(
                f"{greeting}\n\n"
                f"I traced {company}'s buyer path and found one issue worth fixing before driving more traffic: {lower_first(observation)}\n\n"
                f"The first build would be {scope}. {reason} The commercial goal is {outcome}.\n\n"
                f"I can show you {show_on_call} and the implementation order in 15 minutes. Would Tuesday or Wednesday work?\n\n"
                f"{signature}"
            ),
        ),
        Draft(
            key="human_commercial",
            label="Commercial case",
            subject=f"Why this matters commercially for {company}",
            body=(
                f"{greeting}\n\n"
                f"One point from my review of {company}: {lower_first(observation)}\n\n"
                f"{context} The business case is to remove that friction before spending more to attract visitors. We would measure the change against {outcome}.\n\n"
                f"I can bring {show_on_call} and review it with you in 15 minutes. Is Tuesday or Wednesday better?\n\n"
                f"{signature}"
            ),
        ),
        Draft(
            key="human_close_loop",
            label="Close loop",
            subject=f"Close the loop on {possessive(company)} website?",
            body=(
                f"{greeting}\n\n"
                f"I am closing the loop on the website review I prepared for {company}. The finding was: {lower_first(observation)}\n\n"
                f"{context} I have {show_on_call} ready. If {outcome} is a current priority, we can review the scope in 15 minutes and decide whether it justifies a build.\n\n"
                "Worth Tuesday or Wednesday? If it is not a priority, I will close the file.\n\n"
                f"{signature}"
            ),
        ),
    ]


def generate_specific_evidence_drafts(
    lead: dict[str, str],
    audit: dict[str, str],
    page_findings: str,
) -> list[Draft]:
    company = lead.get("business_name", "").strip() or "your business"
    name = lead.get("name", "").strip()
    first_name = name.split()[0] if name else ""
    greeting = f"Hi {first_name}," if first_name else f"Hi {company} team,"
    subject_name = first_name or company
    page = audit.get("evidence_page", "the page").strip() or "the page"
    funnel = audit.get("funnel_sequence", "").strip()
    scope = offer_scope(audit.get("recommended_offer", ""))
    segment = lead.get("segment", "").strip()
    context = buyer_context(segment, audit.get("specific_observation", ""))
    strength = strength_line(segment)
    show = clean_phrase(audit.get("what_to_show_on_call", ""))
    signature = f"{AGENCY_NAME}\n{AGENCY_URL}"
    path_line = f"The current path reads {funnel}." if funnel else "The current path moves from the service page into an enquiry decision."

    return [
        Draft(
            key="specific_finding",
            label="Specific finding",
            subject=f"{subject_name}, your {page.lower().removesuffix(' page')} is still showing template copy",
            body=(
                f"{greeting}\n\n"
                f"I reviewed the path a buyer takes from the {company} homepage to booking a discovery call.\n\n"
                f"{strength}, but {lower_first(page_findings)}\n\n"
                f"{context} {path_line} That creates a trust break immediately before the enquiry decision.\n\n"
                f"We mapped a focused fix: {scope}. I can show you the marked-up {page.lower()} and the proposed funnel in 15 minutes. Would Tuesday or Wednesday work better?\n\n"
                f"{signature}"
            ),
        ),
        Draft(
            key="specific_impact",
            label="Buyer impact",
            subject=f"A trust break on {company}'s {page.lower().removesuffix(' page')}",
            body=(
                f"{greeting}\n\n"
                f"The reason I flagged {company} is visible on the {page.lower()}: {lower_first(page_findings)}\n\n"
                f"{context} {path_line} A visitor can understand the offer and still hesitate because the page looks unfinished at the exact decision point.\n\n"
                f"The useful fix is {scope}, not a general website rebuild. I can walk you through the page edits and funnel sequence in 15 minutes. Can we use Tuesday or Wednesday?\n\n"
                f"{signature}"
            ),
        ),
        Draft(
            key="specific_scope",
            label="Build scope",
            subject=f"The first conversion fix I would make for {company}",
            body=(
                f"{greeting}\n\n"
                f"I traced {company}'s {page.lower()} and found one issue worth fixing before driving more traffic: {lower_first(page_findings)}\n\n"
                f"The first build would be {scope}. {context} {path_line}\n\n"
                f"I have the marked-up page, replacement structure, and funnel sequence ready to show in 15 minutes. Would Tuesday or Wednesday work?\n\n"
                f"{signature}"
            ),
        ),
        Draft(
            key="specific_commercial",
            label="Commercial case",
            subject=f"Why the unfinished {page.lower().removesuffix(' page')} matters",
            body=(
                f"{greeting}\n\n"
                f"One point from my review of {company}: {lower_first(page_findings)}\n\n"
                f"That is not a cosmetic issue. {context} The current path is {funnel or 'a service page into an enquiry form with no visible booking step'}, so the page is asking a qualified visitor to trust an unfinished experience.\n\n"
                f"I can show you the focused fix and how I would measure the path from page view to qualified discovery call in 15 minutes. Is Tuesday or Wednesday better?\n\n"
                f"{signature}"
            ),
        ),
        Draft(
            key="specific_close_loop",
            label="Close loop",
            subject=f"Close the loop on {company}'s {page.lower().removesuffix(' page')}?",
            body=(
                f"{greeting}\n\n"
                f"I am closing the loop on the page review I prepared for {company}. The finding was straightforward: {lower_first(page_findings)}\n\n"
                f"{context} I have the page markup and proposed funnel ready. If improving that path is a priority, we can review the scope in 15 minutes and decide whether it justifies a build.\n\n"
                f"Worth Tuesday or Wednesday? If it is not a priority, I will close the file.\n\n"
                f"{signature}"
            ),
        ),
    ]


def buyer_context(segment: str, observation: str) -> str:
    lowered = observation.lower()
    has_template_issue = any(
        phrase in lowered
        for phrase in ("lorem ipsum", "placeholder", "unfinished", "template copy")
    )
    if segment == "coach" and "executive" in lowered:
        return "For someone considering a six-month coaching engagement, that detail matters before they book."
    if segment == "coach":
        if has_template_issue:
            return "For someone comparing coaching support, an unfinished service page makes the next step harder to trust."
        return "For someone comparing coaching support, that gap appears just before the decision to book."
    if segment == "agency_owner":
        if has_template_issue:
            return "For a prospect comparing specialist partners, unfinished proof or placeholder copy creates an avoidable trust break."
        return "For a prospect comparing specialist partners, that gap makes the next step harder to trust."
    if not has_template_issue:
        return "For someone deciding whether to enquire, that gap appears at the point where intent needs to become an action."
    return "For someone deciding whether to enquire, unfinished page content creates an avoidable trust break."


def strength_line(segment: str) -> str:
    if segment == "coach":
        return "Your positioning and credentials are strong"
    if segment == "agency_owner":
        return "The offer is clear and credible"
    return "The core offer is clear"


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
