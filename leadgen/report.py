from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AuditFinding:
    angle: str
    observation: str
    money_impact: str
    recommended_fix: str


@dataclass(frozen=True)
class MeetingPlay:
    recommended_service: str
    specific_problem: str
    business_impact: str
    what_to_show_on_call: str
    email_subject: str
    meeting_email: str
    call_talk_track: str


def load_lead_rows(input_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for filename in ("leads.csv", "candidates_review.csv"):
        path = input_dir / filename
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows.extend(csv.DictReader(handle))
    return rows


def generate_reports(input_dir: Path, output_dir: Path, limit: int | None = None) -> tuple[int, Path]:
    rows = load_lead_rows(input_dir)
    selected = rows if limit is None else rows[:limit]
    reports_dir = output_dir / "lead_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "audit_report_summary.csv"

    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "lead_id",
            "business_name",
            "website",
            "recommended_service",
            "primary_angle",
            "specific_problem",
            "business_impact",
            "what_to_show_on_call",
            "priority_score",
            "email_subject",
            "meeting_email",
            "call_talk_track",
            "report_path",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index, row in enumerate(selected, start=1):
            lead_id = row.get("lead_id") or f"L{index:06d}"
            findings = build_findings(row)
            report_path = reports_dir / f"{safe_slug(lead_id + '-' + row.get('business_name', 'lead'))}.md"
            primary = findings[0]
            play = build_meeting_play(row, primary, findings)
            report_path.write_text(render_report(row, findings, play), encoding="utf-8")
            writer.writerow(
                {
                    "lead_id": lead_id,
                    "business_name": row.get("business_name", ""),
                    "website": row.get("website", ""),
                    "recommended_service": play.recommended_service,
                    "primary_angle": primary.angle,
                    "specific_problem": play.specific_problem,
                    "business_impact": play.business_impact,
                    "what_to_show_on_call": play.what_to_show_on_call,
                    "priority_score": priority_score(row, findings),
                    "email_subject": play.email_subject,
                    "meeting_email": play.meeting_email,
                    "call_talk_track": play.call_talk_track,
                    "report_path": str(report_path),
                }
            )
    return len(selected), summary_path


def build_findings(row: dict[str, str]) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    reasons = row.get("score_reasons", "").lower()
    missing = row.get("missing_reason", "").lower()
    segment = row.get("segment", "")
    reviews = parse_int(row.get("maps_reviews", ""))
    rating = row.get("maps_rating", "")
    website_score = parse_int(row.get("website_score", ""))

    findings.extend(segment_growth_findings(row))

    if not row.get("booking_url"):
        findings.append(
            AuditFinding(
                angle="booking_friction",
                observation="I could not find a clear booking or appointment path on the public pages checked.",
                money_impact="People who are ready to buy may leave instead of becoming booked calls, appointments, or quote requests.",
                recommended_fix="Put one revenue action above the fold: Book now, Request a quote, or Schedule a consultation. Repeat it near testimonials and service sections.",
            )
        )

    if "no_contact_channel" in missing or not any(row.get(field) for field in ("email", "phone", "contact_page")):
        findings.append(
            AuditFinding(
                angle="lost_inquiries",
                observation="The public pages checked do not show an easy email, phone, or contact-page path.",
                money_impact="High-intent visitors can be lost at the exact moment they are trying to contact the business.",
                recommended_fix="Add a persistent contact action, shorten the contact form, and show phone/email near the main call to action.",
            )
        )

    if reviews and reviews >= 25 and not row.get("booking_url"):
        findings.append(
            AuditFinding(
                angle="review_to_booking_gap",
                observation=f"The business has visible review demand signals ({rating or 'rated'} with {reviews} reviews), but the public pages checked do not show a direct booking path.",
                money_impact="Strong reviews create buying intent; without a direct action, that trust may not convert into revenue.",
                recommended_fix="Place review proof beside the booking CTA and add a short 'why customers choose us' section before the form.",
            )
        )

    if website_score >= 35 or "website_opportunity" in reasons:
        findings.append(
            AuditFinding(
                angle="website_revenue_leak",
                observation="The website shows signals that it may be under-converting compared with the business demand it receives.",
                money_impact="A clearer offer, faster path to action, and better trust proof can turn existing traffic into more paid work without needing more ads.",
                recommended_fix="Rebuild the first screen around one profitable offer, one proof point, and one action button tied to bookings or quotes.",
            )
        )

    if segment == "agency_owner":
        findings.append(
            AuditFinding(
                angle="agency_pipeline_clarity",
                observation="The agency positioning can be turned into a stronger client-acquisition path.",
                money_impact="Prospects need to quickly understand the niche, proof, and next step before they book a sales call.",
                recommended_fix="Make the homepage sell one outcome, show 2-3 proof points, and route visitors into a clear discovery-call CTA.",
            )
        )
    elif segment in {"small_business", "shop_owner"}:
        findings.append(
            AuditFinding(
                angle="local_revenue_capture",
                observation="The business can capture more local demand by making the next buying step more obvious.",
                money_impact="Local visitors are often comparing options quickly; a clearer page can win more calls, bookings, and walk-ins.",
                recommended_fix="Show top services, price/booking expectations where possible, reviews, location, and a sticky call or booking action.",
            )
        )
    elif segment in {"coach", "tutor", "creator"}:
        findings.append(
            AuditFinding(
                angle="offer_conversion",
                observation="The offer can be made easier to understand and buy.",
                money_impact="A visitor who understands the outcome and next step is more likely to book, apply, subscribe, or purchase.",
                recommended_fix="Lead with the paid outcome, add proof close to the CTA, and remove extra steps before booking or checkout.",
            )
        )

    return prioritize_findings(dedupe_findings(findings), row)[:5]


def segment_growth_findings(row: dict[str, str]) -> list[AuditFinding]:
    segment = row.get("segment", "")
    category = row.get("category", "").lower()
    website_score = parse_int(row.get("website_score", ""))
    findings = [
        AuditFinding(
            angle="seo_service_pages",
            observation="The business may be able to capture more search demand with clearer service pages built around high-intent keywords.",
            money_impact="People searching for a specific service are closer to buying than generic homepage visitors.",
            recommended_fix="Create or improve dedicated pages for the highest-value services, each with proof, FAQs, location/service-area language, and a clear next step.",
        ),
        AuditFinding(
            angle="automation_followup",
            observation="New inquiries may not be followed up with a structured automated sequence.",
            money_impact="Speed-to-lead and consistent follow-up can recover prospects who do not book or buy on the first visit.",
            recommended_fix="Add an automation that sends an instant confirmation, reminder, proof message, and follow-up offer after every form, call, or booking click.",
        ),
    ]

    if segment in {"small_business", "shop_owner", "tutor"} or category:
        findings.append(
            AuditFinding(
                angle="local_seo_pages",
                observation="The business can likely win more local intent with pages for key services and service areas.",
                money_impact="Local search pages can bring in buyers who already know what they need and are comparing providers nearby.",
                recommended_fix="Build service + city pages for the most profitable offers, then connect them to reviews, photos, FAQs, and a direct inquiry path.",
            )
        )

    if segment == "agency_owner":
        findings.append(
            AuditFinding(
                angle="case_study_pages",
                observation="The agency can turn past work into stronger sales assets with sharper case study or industry pages.",
                money_impact="Specific proof helps prospects justify a sales call faster than a general portfolio.",
                recommended_fix="Create case study pages around problem, process, result, timeline, and a call-to-action for similar companies.",
            )
        )

    if segment in {"coach", "creator", "tutor"}:
        findings.append(
            AuditFinding(
                angle="lead_magnet_automation",
                observation="The offer could benefit from a simple lead capture and nurture path before asking for a call or purchase.",
                money_impact="Not every visitor is ready today; a useful resource plus follow-up sequence can convert later buyers.",
                recommended_fix="Create a short resource, quiz, checklist, or diagnostic and connect it to an email sequence that leads to the paid offer.",
            )
        )

    if website_score >= 35:
        findings.append(
            AuditFinding(
                angle="website_refresh",
                observation="The site has signals that the page experience or content structure may be holding back conversions.",
                money_impact="A clearer website can improve results from traffic the business already has.",
                recommended_fix="Refresh the homepage and key service pages around offer clarity, proof, speed, mobile layout, and conversion tracking.",
            )
        )

    return findings


def prioritize_findings(findings: list[AuditFinding], row: dict[str, str]) -> list[AuditFinding]:
    segment = row.get("segment", "")
    preferred = ["seo_service_pages", "automation_followup", "local_seo_pages", "website_refresh"]
    if segment == "agency_owner":
        preferred = ["case_study_pages", "seo_service_pages", "automation_followup", "agency_pipeline_clarity"]
    elif segment in {"coach", "creator", "tutor"}:
        preferred = ["lead_magnet_automation", "seo_service_pages", "automation_followup", "offer_conversion"]
    rank = {angle: index for index, angle in enumerate(preferred)}
    return sorted(findings, key=lambda finding: rank.get(finding.angle, 50))


def build_meeting_play(row: dict[str, str], finding: AuditFinding, findings: list[AuditFinding]) -> MeetingPlay:
    business = short_business_name(row)
    service = recommended_service(finding)
    problem = meeting_problem(finding)
    impact = meeting_impact(finding)
    show = what_to_show_on_call(finding, row)
    subject = meeting_subject(row, finding)
    email = meeting_email(row, finding)
    talk_track = call_talk_track(row, finding, findings)
    return MeetingPlay(
        recommended_service=service,
        specific_problem=problem,
        business_impact=impact,
        what_to_show_on_call=show,
        email_subject=subject,
        meeting_email=email,
        call_talk_track=talk_track,
    )


def render_report(row: dict[str, str], findings: list[AuditFinding], play: MeetingPlay) -> str:
    business_name = row.get("business_name") or "This business"
    website = row.get("website", "")
    primary = findings[0]
    segment_label = segment_name(row.get("segment", ""))
    score = priority_score(row, findings)
    lines = [
        f"# Revenue Opportunity Audit: {business_name}",
        "",
        f"Website: {website}",
        f"Business type: {segment_label}",
        f"Priority score: {score}/100",
        "",
        "## Meeting Goal",
        "",
        f"Book a short strategy call around: {play.recommended_service}",
        "",
        f"- Specific problem: {play.specific_problem}",
        f"- Business impact: {play.business_impact}",
        f"- Show on call: {play.what_to_show_on_call}",
        "",
        "## Executive Summary",
        "",
        revenue_hypothesis(row, findings),
        "",
        "The main opportunity is not a prettier website. It is making it easier for existing visitors to become calls, bookings, quote requests, or sales conversations.",
        "",
        "## Highest-Value Opportunity",
        "",
        f"- Angle: {titleize(primary.angle)}",
        f"- Why it matters: {primary.money_impact}",
        f"- First fix to test: {primary.recommended_fix}",
        "",
        "## Evidence From The Lead Data",
        "",
        *evidence_lines(row),
        "",
        "## What I Noticed",
        "",
    ]
    for index, finding in enumerate(findings, start=1):
        lines.extend(
            [
                f"### {index}. {titleize(finding.angle)}",
                "",
                f"- Observation: {finding.observation}",
                f"- Revenue impact: {finding.money_impact}",
                f"- Suggested fix: {finding.recommended_fix}",
                "",
            ]
        )
    lines.extend(
        [
            "## 7-Day Revenue Fix Plan",
            "",
            *quick_win_plan(row, findings),
            "",
            "## Suggested Homepage Structure",
            "",
            *homepage_structure(row),
            "",
            "## Offer Positioning To Test",
            "",
            *offer_positioning(row),
            "",
            "## Follow-Up Questions",
            "",
            *follow_up_questions(row, findings),
            "",
            "## Meeting Email",
            "",
            play.meeting_email,
            "",
            "## Call Talk Track",
            "",
            play.call_talk_track,
            "",
        ]
    )
    return "\n".join(lines)


def meeting_subject(row: dict[str, str], finding: AuditFinding) -> str:
    business = short_business_name(row)
    subjects = {
        "seo_service_pages": f"quick SEO idea for {business}",
        "automation_followup": f"follow-up idea for {business}",
        "local_seo_pages": f"local SEO idea for {business}",
        "case_study_pages": f"case study idea for {business}",
        "lead_magnet_automation": f"lead capture idea for {business}",
        "website_refresh": f"website structure idea for {business}",
        "booking_friction": f"conversion idea for {business}",
        "lost_inquiries": f"inquiry flow idea for {business}",
        "review_to_booking_gap": f"review conversion idea for {business}",
        "website_revenue_leak": f"website conversion idea for {business}",
        "agency_pipeline_clarity": f"sales page idea for {business}",
        "local_revenue_capture": f"local conversion idea for {business}",
        "offer_conversion": f"offer page idea for {business}",
    }
    return subjects.get(finding.angle, f"quick idea for {business}")


def outreach_subject(row: dict[str, str], finding: AuditFinding) -> str:
    return meeting_subject(row, finding)


def outreach_opener(row: dict[str, str], finding: AuditFinding) -> str:
    business = short_business_name(row)
    return f"I made a short note for {business}: {finding.observation}"


def outreach_message(row: dict[str, str], finding: AuditFinding) -> str:
    business = short_business_name(row)
    return "\n\n".join(
        [
            "Hi,",
            f"I made a short revenue note for {business}.",
            f"The main thing: {plain_observation(finding)}",
            f"Why I think it matters: {plain_impact(finding)}",
            f"What I would change first: {plain_fix(finding)}",
            "I can send the 1-page version if you want it.",
        ]
    )


def short_outreach_message(row: dict[str, str], finding: AuditFinding) -> str:
    business = short_business_name(row)
    return (
        f"Hi, I made a short revenue note for {business}. "
        f"{sentence_case(plain_observation(finding))} {sentence_case(plain_fix(finding))} "
        f"I can send the 1-page version if useful."
    )


def meeting_email(row: dict[str, str], finding: AuditFinding) -> str:
    business = short_business_name(row)
    return "\n\n".join(
        [
            "Hi,",
            f"I checked {business} and noticed something specific: {strip_period(meeting_problem(finding))}.",
            f"The reason I am mentioning it is that {strip_period(meeting_impact(finding))}.",
            f"We usually help with this through {recommended_service(finding).lower()}.",
            f"Open to a quick 10-minute call? I can show you {strip_period(what_to_show_on_call(finding, row))}.",
        ]
    )


def recommended_service(finding: AuditFinding) -> str:
    services = {
        "seo_service_pages": "SEO service-page buildout",
        "local_seo_pages": "Local SEO landing pages",
        "automation_followup": "Lead follow-up automation",
        "lead_magnet_automation": "Lead capture and nurture automation",
        "case_study_pages": "Case study and proof-page buildout",
        "website_refresh": "Website conversion restructure",
        "website_revenue_leak": "Website conversion restructure",
        "agency_pipeline_clarity": "Sales page and offer positioning",
        "booking_friction": "Conversion path optimization",
        "lost_inquiries": "Inquiry flow optimization",
        "review_to_booking_gap": "Review-to-booking conversion",
        "local_revenue_capture": "Local landing page and conversion flow",
        "offer_conversion": "Offer page conversion improvement",
    }
    return services.get(finding.angle, "Website growth strategy")


def meeting_problem(finding: AuditFinding) -> str:
    problems = {
        "seo_service_pages": "the main services could be split into focused pages that target what buyers actually search for.",
        "local_seo_pages": "there may be missing service-and-location pages for local search intent.",
        "automation_followup": "new inquiries may not have a structured follow-up path after the first form, call, or booking click.",
        "lead_magnet_automation": "interested visitors who are not ready to book may be leaving without entering a nurture flow.",
        "case_study_pages": "past work could be doing more sales work if it were packaged as case studies with problem, process, and result.",
        "website_refresh": "the page structure could do more to connect search intent, proof, and the next action.",
        "website_revenue_leak": "the first screen could make the offer, proof, and next action clearer.",
        "agency_pipeline_clarity": "the offer and discovery-call path could be sharper for qualified prospects.",
        "booking_friction": "the booking or quote path could be easier to find for ready buyers.",
        "lost_inquiries": "the contact path could be clearer for someone ready to ask a buying question.",
        "review_to_booking_gap": "the trust from reviews could be connected more directly to the booking or inquiry action.",
        "local_revenue_capture": "local visitors could reach the most profitable service and next step faster.",
        "offer_conversion": "the offer could be easier to understand and act on.",
    }
    return problems.get(finding.angle, plain_observation(finding))


def meeting_impact(finding: AuditFinding) -> str:
    impacts = {
        "seo_service_pages": "service-specific searches usually come from people with clearer intent than broad homepage traffic.",
        "local_seo_pages": "local buyers often search by service and city before choosing who to contact.",
        "automation_followup": "many leads do not convert on the first touch, and speed plus consistency can recover missed opportunities.",
        "lead_magnet_automation": "not every good prospect is ready today, but a useful capture path gives the business more chances to convert them later.",
        "case_study_pages": "specific proof reduces trust friction and can make a sales call easier to justify.",
        "website_refresh": "better page structure can improve both search visibility and inquiry rate from the same traffic.",
        "website_revenue_leak": "clearer offer and proof can increase inquiries without needing more traffic.",
        "agency_pipeline_clarity": "qualified prospects need to understand the outcome and trust the proof before they book a call.",
        "booking_friction": "extra steps between interest and action can reduce booked calls, quotes, or appointments.",
        "lost_inquiries": "ready buyers should not have to hunt for a way to contact the business.",
        "review_to_booking_gap": "strong proof works best when it sits near the action you want buyers to take.",
        "local_revenue_capture": "local customers compare fast, so the clearest path often wins the inquiry.",
        "offer_conversion": "clear outcomes make it easier for people to book, apply, or buy.",
    }
    return impacts.get(finding.angle, plain_impact(finding))


def what_to_show_on_call(finding: AuditFinding, row: dict[str, str]) -> str:
    business_type = segment_name(row.get("segment", "")).lower()
    show = {
        "seo_service_pages": f"the first 3 service pages I would build for a {business_type} and how I would structure them.",
        "local_seo_pages": "which service + city pages I would prioritize and what each page should include.",
        "automation_followup": "a simple follow-up sequence for new inquiries: instant reply, reminder, proof, and second CTA.",
        "lead_magnet_automation": "a capture offer and nurture sequence that moves undecided visitors toward a call.",
        "case_study_pages": "how I would turn 2-3 projects into proof pages that support sales calls.",
        "website_refresh": "the homepage structure I would use to connect search intent, proof, and conversion.",
        "website_revenue_leak": "the first-screen changes I would test to make the offer and next action clearer.",
        "agency_pipeline_clarity": "the offer, proof, and discovery-call section I would put on the page.",
        "booking_friction": "where I would place the main CTA and what copy I would test around it.",
        "lost_inquiries": "the inquiry flow I would simplify so buyers can contact faster.",
        "review_to_booking_gap": "where I would place reviews so they support the booking or inquiry action.",
        "local_revenue_capture": "the local page layout I would use to turn visitors into calls or bookings.",
        "offer_conversion": "the offer page structure I would test to make the next step obvious.",
    }
    return show.get(finding.angle, "the fastest changes I would make first")


def call_talk_track(row: dict[str, str], finding: AuditFinding, findings: list[AuditFinding]) -> str:
    business = short_business_name(row)
    secondary = [item for item in findings[1:3]]
    secondary_text = "; ".join(f"{recommended_service(item)}: {strip_period(meeting_problem(item))}" for item in secondary)
    if secondary_text:
        secondary_text = f"\n\nSecondary angles if the first one does not land: {secondary_text}."
    return (
        f"Call goal: book a next-step project conversation around {recommended_service(finding)}.\n\n"
        f"Open by saying you looked at {business} and saw one practical growth opportunity: {strip_period(meeting_problem(finding))}. "
        f"Then explain the money reason: {strip_period(meeting_impact(finding))}. "
        f"Show them: {strip_period(what_to_show_on_call(finding, row))}. "
        f"Close by asking whether they want you to map the first version for their business."
        f"{secondary_text}"
    )


def strip_period(value: str) -> str:
    return value.strip().rstrip(".")


def plain_observation(finding: AuditFinding) -> str:
    observations = {
        "seo_service_pages": "there may be room to turn the main services into stronger search pages.",
        "automation_followup": "the follow-up after an inquiry could probably be more systematic.",
        "local_seo_pages": "there may be room to create stronger service and location pages for local search.",
        "case_study_pages": "the past work could be packaged into sharper proof pages.",
        "lead_magnet_automation": "there may be a better way to capture visitors who are interested but not ready to book.",
        "website_refresh": "the page structure could do more to support search, trust, and conversion.",
        "booking_friction": "the booking or quote path could be easier to find.",
        "lost_inquiries": "the contact path could be clearer for someone ready to ask a question.",
        "review_to_booking_gap": "the reviews create trust, but the next booking step could be closer to that proof.",
        "website_revenue_leak": "the first screen could do more to turn visitors into inquiries.",
        "agency_pipeline_clarity": "the offer and discovery-call path could be sharper.",
        "local_revenue_capture": "local visitors could get to the next step faster.",
        "offer_conversion": "the offer could be easier to understand and act on.",
    }
    return observations.get(finding.angle, finding.observation[:1].lower() + finding.observation[1:])


def plain_impact(finding: AuditFinding) -> str:
    impacts = {
        "seo_service_pages": "specific service pages can bring in visitors who are already searching for that exact help.",
        "automation_followup": "many leads do not convert on the first touch, so consistent follow-up can recover missed revenue.",
        "local_seo_pages": "local buyers often search by service and city before choosing who to contact.",
        "case_study_pages": "specific proof can make it easier for prospects to trust the offer and book a call.",
        "lead_magnet_automation": "capturing undecided visitors gives the business more chances to turn them into customers later.",
        "website_refresh": "better structure can improve both search visibility and the percentage of visitors who inquire.",
        "booking_friction": "when someone is ready, every extra step can reduce booked calls or quote requests.",
        "lost_inquiries": "ready buyers should not have to hunt for a way to contact the business.",
        "review_to_booking_gap": "strong proof works best when it sits right next to the action you want people to take.",
        "website_revenue_leak": "small clarity changes can increase inquiries without needing more traffic.",
        "agency_pipeline_clarity": "qualified prospects need to understand the outcome before they book a call.",
        "local_revenue_capture": "local customers compare fast, so the clearest path often wins.",
        "offer_conversion": "clear outcomes make it easier for people to book, apply, or buy.",
    }
    return impacts.get(finding.angle, finding.money_impact[:1].lower() + finding.money_impact[1:])


def plain_fix(finding: AuditFinding) -> str:
    fixes = {
        "seo_service_pages": "build dedicated pages for the highest-value services with proof, FAQs, and search-focused copy.",
        "automation_followup": "connect forms and booking actions to an instant follow-up sequence with reminders and proof.",
        "local_seo_pages": "create service and city pages for the most profitable offers and connect them to reviews.",
        "case_study_pages": "turn 2-3 strong projects into pages with the problem, result, timeline, and next step.",
        "lead_magnet_automation": "add a useful checklist, quiz, or diagnostic and follow up with a short email sequence.",
        "website_refresh": "restructure the homepage and core pages around search intent, proof, and clear next actions.",
        "booking_friction": "put one clear Book, Quote, or Call action in the first screen and repeat it after proof.",
        "lost_inquiries": "make phone, email, or a short form visible from the main pages.",
        "review_to_booking_gap": "place the best reviews beside the booking or quote button.",
        "website_revenue_leak": "rewrite the first screen around one offer, one proof point, and one action.",
        "agency_pipeline_clarity": "lead with the niche, result, proof, and discovery-call button.",
        "local_revenue_capture": "show top services, reviews, location, and a call/booking action together.",
        "offer_conversion": "lead with the paid outcome and remove extra steps before booking.",
    }
    return fixes.get(finding.angle, finding.recommended_fix[:1].lower() + finding.recommended_fix[1:])


def sentence_case(value: str) -> str:
    if not value:
        return value
    return value[:1].upper() + value[1:]


def revenue_hypothesis(row: dict[str, str], findings: list[AuditFinding]) -> str:
    business = short_business_name(row)
    reviews = parse_int(row.get("maps_reviews", ""))
    score = priority_score(row, findings)
    if reviews >= 25:
        return (
            f"{business} already shows demand signals through its review footprint. "
            f"The audit priority is {score}/100 because trust appears to exist, but the next buying step can be made clearer so more visitors become bookings or inquiries."
        )
    if row.get("source_provider") == "serpapi_maps":
        return (
            f"{business} is visible in local search. The fastest money opportunity is improving the path from discovery to contact, booking, or quote request."
        )
    if row.get("segment") == "agency_owner":
        return (
            f"{business} can likely improve qualified sales conversations by making the offer, proof, and discovery-call path sharper on the website."
        )
    return (
        f"{business} has a practical conversion opportunity: reduce friction between a visitor landing on the site and taking the next paid action."
    )


def priority_score(row: dict[str, str], findings: list[AuditFinding]) -> int:
    score = 35
    if not row.get("booking_url"):
        score += 18
    if not any(row.get(field) for field in ("email", "phone", "contact_page")):
        score += 16
    if parse_int(row.get("maps_reviews", "")) >= 25:
        score += 14
    if parse_int(row.get("website_score", "")) >= 35:
        score += 12
    if row.get("confidence") == "high":
        score += 5
    score += min(10, len(findings) * 2)
    return min(score, 100)


def evidence_lines(row: dict[str, str]) -> list[str]:
    lines = []
    lines.append(f"- Source: {row.get('source_provider') or 'lead export'}")
    if row.get("category"):
        lines.append(f"- Category: {row.get('category')}")
    if row.get("maps_rating") or row.get("maps_reviews"):
        lines.append(f"- Review signal: {row.get('maps_rating') or 'rated'} rating, {row.get('maps_reviews') or 'unknown'} reviews")
    lines.append(f"- Booking path found: {'yes' if row.get('booking_url') else 'no'}")
    lines.append(f"- Contact path found: {'yes' if any(row.get(field) for field in ('email', 'phone', 'contact_page')) else 'no'}")
    if row.get("website_score"):
        lines.append(f"- Website opportunity score: {row.get('website_score')}/100")
    if row.get("score_reasons"):
        lines.append(f"- Matching signals: {row.get('score_reasons')}")
    return lines


def quick_win_plan(row: dict[str, str], findings: list[AuditFinding]) -> list[str]:
    plan = [
        "1. Pick one money action for the site: book a call, request a quote, schedule an appointment, or buy now.",
        "2. Put that action in the first screen with a clear outcome statement.",
        "3. Add trust proof directly beside the action: reviews, client logos, before/after results, or a short testimonial.",
    ]
    if not any(row.get(field) for field in ("email", "phone", "contact_page")):
        plan.append("4. Add a low-friction contact path: phone, email, or a short form visible from every key page.")
    else:
        plan.append("4. Move the strongest existing contact path closer to the main call to action.")
    if not row.get("booking_url"):
        plan.append("5. Add a direct booking or quote-request link and repeat it after services, proof, and FAQ sections.")
    else:
        plan.append("5. Add context before the booking link so visitors know what happens after they click.")
    plan.extend(
        [
            "6. Rewrite the first paragraph around the buyer's desired result, not general company background.",
            "7. Track calls, form submissions, and booking clicks so the business can see whether the change produces more revenue opportunities.",
        ]
    )
    return plan


def homepage_structure(row: dict[str, str]) -> list[str]:
    action = "Book a call" if row.get("segment") in {"agency_owner", "coach", "creator"} else "Request a quote or book now"
    return [
        f"1. Hero: clear outcome + {action} button",
        "2. Proof strip: reviews, results, recognizable clients, or years in business",
        "3. Services/offers: 3-5 options written as buyer outcomes",
        "4. Why choose us: specific reasons a buyer should trust the business",
        "5. Conversion section: form, phone, booking link, or quote request",
        "6. FAQ: answer friction questions that stop people from contacting",
    ]


def offer_positioning(row: dict[str, str]) -> list[str]:
    segment = row.get("segment", "")
    if segment == "agency_owner":
        return [
            "Primary promise: Turn more qualified website visitors into booked discovery calls.",
            "CTA to test: Get a free conversion teardown.",
            "Proof to show: client outcomes, niches served, and before/after metrics.",
        ]
    if segment in {"small_business", "shop_owner"}:
        return [
            "Primary promise: Make it easier for local customers to choose, contact, and book.",
            "CTA to test: Book now or request a fast quote.",
            "Proof to show: reviews, service photos, location, guarantees, and response time.",
        ]
    if segment in {"coach", "tutor", "creator"}:
        return [
            "Primary promise: Clarify the outcome people get from the offer.",
            "CTA to test: Apply, book a call, or start with a low-friction intro offer.",
            "Proof to show: testimonials, transformation examples, credentials, and who the offer is for.",
        ]
    return [
        "Primary promise: Make the next profitable action obvious.",
        "CTA to test: Request a quote or schedule a consultation.",
        "Proof to show: testimonials, reviews, outcomes, and simple process steps.",
    ]


def follow_up_questions(row: dict[str, str], findings: list[AuditFinding]) -> list[str]:
    return [
        "1. What is one new customer, booking, or qualified call worth to the business?",
        "2. Which service or offer has the highest margin and should get the most website attention?",
        "3. Where do most inquiries currently come from: Google, referrals, ads, social, or repeat customers?",
        "4. What percentage of inquiries become paying customers?",
        "5. Is the business currently tracking form submissions, booking clicks, and phone calls?",
    ]


def segment_name(segment: str) -> str:
    names = {
        "agency_owner": "Agency or studio",
        "coach": "Coach or consultant",
        "creator": "Creator or personal brand",
        "small_business": "Local service business",
        "shop_owner": "Shop or ecommerce business",
        "tutor": "Tutor or education business",
    }
    return names.get(segment, segment or "Unknown")


def dedupe_findings(findings: list[AuditFinding]) -> list[AuditFinding]:
    seen: set[str] = set()
    unique: list[AuditFinding] = []
    for finding in findings:
        if finding.angle in seen:
            continue
        seen.add(finding.angle)
        unique.append(finding)
    return unique


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "lead-report"


def titleize(value: str) -> str:
    return value.replace("_", " ").title()


def short_business_name(row: dict[str, str]) -> str:
    name = row.get("business_name", "").strip()
    return name[:60] if name else "your business"


def parse_int(value: str) -> int:
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return 0
