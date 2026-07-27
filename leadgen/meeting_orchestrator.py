from __future__ import annotations

import csv
import json
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from .filters import blocked_domain, public_sector_domain, unsuitable_outreach_email
from .report import load_lead_rows
from .score import GENERIC_PAGE_TITLES, choose_business_name, cleanup_title
from .urltools import domain_key, normalize_url, same_site, site_root_url


SERVICE_PAGE_OFFER = "High-Intent Service Page Pack"
CONVERSION_OFFER = "Website Conversion Sprint"
AUTOMATION_OFFER = "Lead Response Automation Setup"

AGENCY_NAME = "NexStudio"
AGENCY_URL = "www.nexstudio.work"

PRICE_RANGES = {
    SERVICE_PAGE_OFFER: "$1,200-$1,600",
    CONVERSION_OFFER: "$1,000-$1,500",
    AUTOMATION_OFFER: "$1,500-$2,000",
}

QUEUE_FIELDS = [
    "lead_id",
    "source_lead_id",
    "business_name",
    "contact_name",
    "website",
    "email",
    "phone",
    "outreach_channel",
    "segment",
    "recommended_offer",
    "price_range",
    "specific_observation",
    "evidence_page",
    "page_findings",
    "funnel_sequence",
    "business_reason",
    "evidence_url",
    "evidence_summary",
    "what_to_show_on_call",
    "email_subject",
    "meeting_email",
    "call_notes",
    "priority_score",
    "confidence",
    "qualification_reasons",
    "audited_at",
    "send_status",
    "report_path",
]

REVIEW_FIELDS = [
    "source_lead_id",
    "business_name",
    "website",
    "email",
    "phone",
    "qualification_status",
    "qualification_reasons",
    "recommended_offer",
    "confidence",
    "audited_at",
]


@dataclass(frozen=True)
class WebsiteSignals:
    url: str
    title: str = ""
    site_name: str = ""
    description: str = ""
    text: str = ""
    links: tuple[str, ...] = ()
    pages_found: tuple[str, ...] = ()
    service_terms: tuple[str, ...] = ()
    website_service_terms: tuple[str, ...] = ()
    has_cta: bool = False
    has_proof: bool = False
    has_form: bool = False
    has_booking: bool = False
    has_chat: bool = False
    has_analytics: bool = False
    has_lead_capture: bool = False
    has_contact_path: bool = False
    has_service_page: bool = False
    has_location_page: bool = False
    has_followup_signal: bool = False
    evidence_page: str = ""
    page_findings: tuple[str, ...] = ()
    funnel_sequence: str = ""
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class OfferMatch:
    recommended_offer: str
    specific_observation: str
    business_reason: str
    what_to_show_on_call: str
    priority_score: int
    confidence: str


@dataclass(frozen=True)
class LeadQualification:
    status: str
    reasons: tuple[str, ...]
    channel: str
    score: int


class SignalHTMLParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self.site_name = ""
        self.description = ""
        self.links: list[str] = []
        self.embeds: list[str] = []
        self.text_parts: list[str] = []
        self.has_form = False
        self.has_proof = False
        self._in_title = False
        self._hidden_depth = 0
        self._suppressed_depth = 0
        self._tag_stack: list[tuple[str, bool, bool]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        lower_tag = tag.lower()
        hidden_here = element_is_hidden(attrs_dict)
        suppressed_here = lower_tag in NON_CONTENT_TAGS
        if lower_tag not in VOID_TAGS:
            self._tag_stack.append((lower_tag, hidden_here, suppressed_here))
            if hidden_here:
                self._hidden_depth += 1
            if suppressed_here:
                self._suppressed_depth += 1
        if lower_tag == "title":
            self._in_title = True
        if lower_tag == "meta":
            meta_name = (attrs_dict.get("name") or attrs_dict.get("property", "")).lower()
            if meta_name == "description":
                self.description = attrs_dict.get("content", "")
            if meta_name == "og:site_name":
                self.site_name = attrs_dict.get("content", "")
        if lower_tag in {"script", "iframe"} and attrs_dict.get("src"):
            self.embeds.append(attrs_dict["src"])
        if not self._content_is_visible():
            return
        element_descriptor = " ".join(
            [attrs_dict.get("class", ""), attrs_dict.get("id", ""), attrs_dict.get("aria-label", "")]
        ).lower()
        if contains_any(element_descriptor, PROOF_MARKERS):
            self.has_proof = True
        if lower_tag == "a" and attrs_dict.get("href"):
            href = attrs_dict["href"].strip()
            if href.startswith(("mailto:", "tel:")):
                self.links.append(href)
            elif href and not href.startswith(("javascript:", "#")):
                self.links.append(normalize_url(href, self.base_url))
        if lower_tag == "form":
            self.has_form = True
        if lower_tag in {"form", "input", "textarea", "select", "button"}:
            label = " ".join(value for value in attrs_dict.values() if value)
            self.text_parts.append(f"{lower_tag} {label}".strip())

    def handle_endtag(self, tag: str) -> None:
        lower_tag = tag.lower()
        if lower_tag == "title":
            self._in_title = False
        for index in range(len(self._tag_stack) - 1, -1, -1):
            if self._tag_stack[index][0] != lower_tag:
                continue
            removed = self._tag_stack[index:]
            del self._tag_stack[index:]
            self._hidden_depth -= sum(1 for _, hidden, _ in removed if hidden)
            self._suppressed_depth -= sum(1 for _, _, suppressed in removed if suppressed)
            break

    def handle_data(self, data: str) -> None:
        clean = " ".join(data.split())
        if not clean:
            return
        if self._in_title:
            self.title += clean + " "
        if self._content_is_visible():
            self.text_parts.append(clean)

    def _content_is_visible(self) -> bool:
        return self._hidden_depth == 0 and self._suppressed_depth == 0


def run_meeting_orchestrator(
    input_dir: Path,
    out_dir: Path,
    max_leads: int | None = None,
    html_by_url: dict[str, str] | None = None,
    crawl_workers: int = 8,
) -> tuple[int, Path]:
    leads = dedupe_lead_rows(row for row in load_lead_rows(input_dir) if row.get("website"))
    selected = leads if max_leads is None else leads[:max_leads]
    out_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = out_dir / "lead_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    for stale_report in reports_dir.glob("*.md"):
        stale_report.unlink()
    csv_path = out_dir / "meeting_queue.csv"
    jsonl_path = out_dir / "meeting_queue.jsonl"
    review_path = out_dir / "research_queue.csv"
    queued = 0
    signals_by_index = inspect_selected_websites(
        selected,
        html_by_url=html_by_url,
        crawl_workers=crawl_workers,
    )

    with (
        csv_path.open("w", encoding="utf-8", newline="") as csv_handle,
        jsonl_path.open("w", encoding="utf-8") as jsonl_handle,
        review_path.open("w", encoding="utf-8", newline="") as review_handle,
    ):
        writer = csv.DictWriter(csv_handle, fieldnames=QUEUE_FIELDS)
        review_writer = csv.DictWriter(review_handle, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        review_writer.writeheader()

        for source_index, source_lead in enumerate(selected, start=1):
            source_lead_id = source_lead.get("lead_id") or f"L{source_index:06d}"
            blocked = blocked_domain(source_lead.get("website", ""))
            if blocked:
                review_writer.writerow(
                    review_row(
                        source_lead_id,
                        source_lead,
                        "rejected",
                        (f"directory_or_profile_domain:{blocked}",),
                    )
                )
                continue
            public_sector = public_sector_domain(source_lead.get("website", ""))
            if public_sector:
                review_writer.writerow(
                    review_row(
                        source_lead_id,
                        source_lead,
                        "rejected",
                        (f"public_sector_domain:{public_sector}",),
                    )
                )
                continue
            unsuitable_email = unsuitable_outreach_email(
                source_lead.get("email", "")
            )
            if unsuitable_email:
                review_writer.writerow(
                    review_row(
                        source_lead_id,
                        source_lead,
                        "rejected",
                        (f"unsuitable_outreach_email:{unsuitable_email}",),
                    )
                )
                continue

            signals = signals_by_index[source_index - 1]
            lead = normalize_lead(source_lead, signals)
            offer = match_offer(lead, signals)
            qualification = qualify_lead(lead, signals, offer)
            if qualification.status != "ready_for_review":
                review_writer.writerow(
                    review_row(
                        source_lead_id,
                        lead,
                        qualification.status,
                        qualification.reasons,
                        offer,
                    )
                )
                continue

            queued += 1
            lead_id = f"M{queued:06d}"
            report_path = reports_dir / f"{safe_slug(lead_id + '-' + lead.get('business_name', 'lead'))}.md"
            row = queue_row(lead_id, source_lead_id, lead, signals, offer, qualification, report_path)
            report_path.write_text(render_meeting_report(lead, signals, offer, row), encoding="utf-8")
            writer.writerow(row)
            jsonl_handle.write(json.dumps(row, sort_keys=True) + "\n")
    return queued, csv_path


def inspect_selected_websites(
    selected: list[dict[str, str]],
    html_by_url: dict[str, str] | None,
    crawl_workers: int,
) -> dict[int, WebsiteSignals]:
    signals_by_index: dict[int, WebsiteSignals] = {}
    inspectable = [
        (index, lead)
        for index, lead in enumerate(selected)
        if (
            not blocked_domain(lead.get("website", ""))
            and not public_sector_domain(lead.get("website", ""))
            and not unsuitable_outreach_email(lead.get("email", ""))
        )
    ]
    workers = max(1, min(crawl_workers, len(inspectable) or 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(inspect_website, lead, html_by_url): (index, lead)
            for index, lead in inspectable
        }
        for future in as_completed(futures):
            index, lead = futures[future]
            try:
                signals_by_index[index] = future.result()
            except Exception as error:
                signals_by_index[index] = WebsiteSignals(
                    url=site_root_url(lead.get("website", "")),
                    service_terms=extract_service_terms(lead),
                    errors=(f"inspection_failed:{type(error).__name__}",),
                )
    return signals_by_index


def dedupe_lead_rows(rows) -> list[dict[str, str]]:
    by_domain: dict[str, dict[str, str]] = {}
    for row in rows:
        key = domain_key(row.get("website", ""))
        if not key:
            continue
        existing = by_domain.get(key)
        if existing is None:
            by_domain[key] = dict(row)
            continue
        for field, value in row.items():
            if value and not existing.get(field):
                existing[field] = value
    return list(by_domain.values())


def normalize_lead(row: dict[str, str], signals: WebsiteSignals) -> dict[str, str]:
    lead = dict(row)
    lead["website"] = signals.url or site_root_url(row.get("website", ""))
    verified_site_name = cleanup_title(signals.site_name)
    if is_plausible_site_name(verified_site_name, lead["website"]):
        lead["business_name"] = verified_site_name
    else:
        lead["business_name"] = choose_business_name(
            signals.title,
            row.get("business_name", ""),
            lead["website"],
        )
    return lead


def inspect_website(row: dict[str, str], html_by_url: dict[str, str] | None = None) -> WebsiteSignals:
    original_url = normalize_url(row.get("website", ""))
    url = site_root_url(original_url)
    errors: list[str] = []
    html = ""
    if html_by_url:
        html = html_by_url.get(url, "") or html_by_url.get(original_url, "") or html_by_url.get(row.get("website", ""), "")
    if not html and not html_by_url:
        html = fetch_html(url, errors)
    if not html:
        return WebsiteSignals(
            url=url,
            service_terms=extract_service_terms(row),
            errors=tuple(errors or ["empty_html"]),
        )

    parser = SignalHTMLParser(url)
    parser.feed(html)
    text = " ".join(parser.text_parts)
    all_links = tuple(sorted(set(parser.links)))
    web_links = tuple(link for link in all_links if link.startswith(("http://", "https://")))
    internal_links = tuple(link for link in web_links if same_site(url, link))
    page_documents = [(url, parser.title.strip(), text, html)]
    followup_urls = [
        link for link in internal_links
        if link != url and len(page_documents) < 6
    ]
    for followup_url in followup_urls:
        page_html = ""
        if html_by_url:
            page_html = html_by_url.get(followup_url, "")
        else:
            page_errors: list[str] = []
            page_html = fetch_html(followup_url, page_errors)
        if not page_html:
            continue
        followup_parser = SignalHTMLParser(followup_url)
        followup_parser.feed(page_html)
        page_documents.append(
            (
                followup_url,
                followup_parser.title.strip(),
                " ".join(followup_parser.text_parts),
                page_html,
            )
        )
    page_findings = [
        item
        for page_url, page_title, page_text, page_html in page_documents
        for item in detect_page_findings(page_url, page_title, page_text, page_html)
    ]
    visible_content = " ".join(
        [parser.title, parser.site_name, parser.description, text, " ".join(all_links)]
    )
    embedded_content = " ".join([visible_content, " ".join(parser.embeds)]).lower()
    technology = " ".join([embedded_content, html]).lower()
    pages_found = tuple(sorted(detect_pages(internal_links)))
    website_service_terms = extract_service_terms({}, visible_content)
    targeted_candidates = extract_target_service_terms(row)
    if row.get("segment") == "coach":
        targeted_service_terms = (
            targeted_candidates if "coach" in visible_content.lower() else ()
        )
    else:
        targeted_service_terms = tuple(
            term for term in targeted_candidates if term in website_service_terms
        )
    service_terms = targeted_service_terms or website_service_terms
    has_booking = contains_any(embedded_content, BOOKING_TERMS)
    has_chat = contains_any(technology, CHAT_TERMS)

    evidence_page = page_findings[0][0] if page_findings else ""
    funnel_sequence = build_funnel_sequence(parser.has_form, has_booking, has_chat, parser.has_proof)

    return WebsiteSignals(
        url=url,
        title=parser.title.strip(),
        site_name=parser.site_name.strip(),
        description=parser.description.strip(),
        text=text[:5000],
        links=internal_links,
        pages_found=pages_found,
        service_terms=service_terms,
        website_service_terms=website_service_terms,
        has_cta=contains_any(visible_content.lower(), CTA_TERMS),
        has_proof=parser.has_proof or contains_any(visible_content.lower(), PROOF_TERMS),
        has_form=parser.has_form,
        has_booking=has_booking,
        has_chat=has_chat,
        has_analytics=contains_any(technology, ANALYTICS_TERMS),
        has_lead_capture=parser.has_form or has_booking or has_chat,
        has_contact_path=parser.has_form
        or contains_any(visible_content.lower(), CONTACT_TERMS),
        has_service_page=any(term_in_links(term, internal_links) for term in service_terms),
        has_location_page="locations" in pages_found,
        has_followup_signal=has_chat,
        evidence_page=evidence_page,
        page_findings=tuple(
            finding for _page, finding in page_findings
        ),
        funnel_sequence=funnel_sequence,
        errors=tuple(errors),
    )


def fetch_html(url: str, errors: list[str]) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "NexStudioResearchBot/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                errors.append(f"non_html:{content_type}")
                return ""
            return response.read(1_000_000).decode("utf-8", errors="ignore")
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        errors.append(f"fetch_failed:{error}")
        return ""


def detect_page_findings(
    page_url: str,
    page_title: str,
    visible_text: str,
    html: str,
) -> list[tuple[str, str]]:
    normalized = " ".join(visible_text.split())
    lowered = normalized.lower()
    if not normalized:
        return []
    label = page_label(page_url, page_title)
    findings: list[str] = []
    if "lorem ipsum" in lowered:
        findings.append("Lorem ipsum sections")
    if "what you can expect" in lowered and (
        "lorem ipsum" in lowered or "placeholder" in lowered or re.search(r"\bLabel\b", normalized)
    ):
        findings.append("an unfinished ‘What you can expect’ area")
    if re.search(r"(?<![a-z])label(?![a-z])", lowered) and "aria-label" not in html.lower():
        findings.append("a placeholder labelled ‘Label’")
    for phrase in ("your content here", "coming soon", "insert text here"):
        if phrase in lowered:
            findings.append(f"the placeholder copy ‘{phrase}’")
    if not findings:
        return []
    return [(label, f"The {label} still contains {join_findings(findings)}.")]


def page_label(page_url: str, page_title: str) -> str:
    path = urlparse(page_url).path.strip("/")
    if path:
        slug = path.rstrip("/").split("/")[-1]
        if slug not in {"", "index", "home"}:
            return f"{re.sub(r'[-_]+', ' ', slug).title()} page"
    title = " ".join(page_title.split()).split("|")[0].strip()
    return f"{title or 'Homepage'} page"


def join_findings(findings: list[str]) -> str:
    if len(findings) == 1:
        return findings[0]
    if len(findings) == 2:
        return f"{findings[0]} and {findings[1]}"
    return ", ".join(findings[:-1]) + f", and {findings[-1]}"


def build_funnel_sequence(
    has_form: bool,
    has_booking: bool,
    has_chat: bool,
    has_proof: bool,
) -> str:
    steps = ["homepage/service page"]
    if has_proof:
        steps.append("proof")
    if has_form:
        steps.append("enquiry form")
    if has_booking:
        steps.append("booking")
    elif has_chat:
        steps.append("chat")
    else:
        steps.append("no visible booking step")
    return " → ".join(steps)


def match_offer(row: dict[str, str], signals: WebsiteSignals) -> OfferMatch:
    if signals.errors:
        return build_offer_match(CONVERSION_OFFER, row, signals, 20, "low")

    scores = {
        SERVICE_PAGE_OFFER: service_page_score(row, signals),
        CONVERSION_OFFER: conversion_score_for(row, signals),
        AUTOMATION_OFFER: automation_score_for(signals),
    }
    recommended_offer = max(scores, key=scores.get)
    score = min(100, scores[recommended_offer])
    confidence = "high" if score >= 70 else "medium" if score >= 50 else "low"
    return build_offer_match(recommended_offer, row, signals, score, confidence)


def build_offer_match(
    offer: str,
    row: dict[str, str],
    signals: WebsiteSignals,
    score: int,
    confidence: str,
) -> OfferMatch:
    service = primary_service_term(row, signals)
    city = row.get("city", "").strip()
    if offer == SERVICE_PAGE_OFFER:
        if service in signals.website_service_terms:
            observation = f"The site mentions {service}, but I could not find a focused {service} page linked from the homepage."
        else:
            observation = f"I could not verify a focused {service} page from the homepage navigation."
        reason = "A page that matches a specific service search can attract higher-intent visitors and give them a clearer path to enquire."
        location = f" in {city}" if city else ""
        show = f"a three-page search plan for {service}{location}, including page topics, sections, proof, and enquiry CTAs"
    elif offer == AUTOMATION_OFFER:
        entry_point = "an enquiry form" if signals.has_form else "a contact or booking path"
        observation = f"The site sends prospects into {entry_point}, but I could not find a visible instant-response option such as chat or text."
        reason = "A faster first response and a consistent reminder sequence can give interested prospects fewer chances to go cold."
        show = "a one-page lead-response flow covering instant email/SMS, reminders, owner alerts, and handoff to a booked call"
    else:
        if signals.errors:
            observation = "I could not reliably inspect the homepage, so this lead needs manual research before any claim is used."
            reason = "Outreach should only use an observation that can be verified on the live site."
            show = "a manually verified homepage review covering offer clarity, proof, CTA, mobile flow, and tracking"
        elif not signals.has_cta:
            observation = f"The homepage explains {service}, but I could not find a clear booking or enquiry action."
            reason = "Interested visitors may understand the service without seeing an obvious next step."
            show = "a marked-up homepage showing the first three changes I would make to the offer, proof, and enquiry path"
        elif not signals.has_proof:
            observation = "The site asks visitors to take action, but I could not find reviews, results, or case-study proof on the homepage."
            reason = "Putting relevant proof beside the next step can reduce hesitation when prospects compare providers."
            show = "a marked-up homepage showing where I would place proof, clarify the offer, and tighten the enquiry path"
        else:
            observation = "The site has a next step and trust signals, but the buying path can still be simplified around one primary action."
            reason = "A more focused path can make it easier for qualified visitors to act without adding more traffic."
            show = "a marked-up homepage showing the three highest-priority conversion changes and how I would measure them"

    if signals.page_findings:
        observation = signals.page_findings[0]
        reason = (
            "A visible template or unfinished section creates a trust break at the point "
            "where a qualified visitor is deciding whether to enquire."
        )
        show = (
            f"the marked-up {signals.evidence_page or 'page'} and a replacement structure "
            f"from {signals.funnel_sequence or 'the first visit'} to a qualified discovery call"
        )

    return OfferMatch(
        recommended_offer=offer,
        specific_observation=observation,
        business_reason=reason,
        what_to_show_on_call=show,
        priority_score=score,
        confidence=confidence,
    )


def qualify_lead(row: dict[str, str], signals: WebsiteSignals, offer: OfferMatch) -> LeadQualification:
    reasons: list[str] = []
    score = 0
    business = row.get("business_name", "").strip()
    channel = outreach_channel(row, signals)

    blocked = blocked_domain(row.get("website", ""))
    if blocked:
        return LeadQualification("rejected", (f"directory_or_profile_domain:{blocked}",), "none", 0)
    public_sector = public_sector_domain(row.get("website", ""))
    if public_sector:
        return LeadQualification(
            "rejected",
            (f"public_sector_domain:{public_sector}",),
            "none",
            0,
        )
    unsuitable_email = unsuitable_outreach_email(row.get("email", ""))
    if unsuitable_email:
        return LeadQualification(
            "rejected",
            (f"unsuitable_outreach_email:{unsuitable_email}",),
            "none",
            0,
        )
    if (
        row.get("segment") == "agency_owner"
        and row.get("workflow") != "agency_partners"
    ):
        return LeadQualification(
            "rejected",
            ("agency_not_verified_by_partner_workflow",),
            channel,
            0,
        )
    if row.get("segment") == "agency_owner" and any(
        term in signals.website_service_terms
        for term in AGENCY_FORBIDDEN_SERVICE_TERMS
    ):
        return LeadQualification(
            "rejected",
            ("agency_offers_web_or_seo_services",),
            channel,
            0,
        )
    if signals.errors:
        return LeadQualification("research_required", signals.errors, channel, 10)
    if (
        offer.recommended_offer != AUTOMATION_OFFER
        and not signals.service_terms
    ):
        return LeadQualification(
            "research_required",
            ("specific_service_not_verified",),
            channel,
            20,
        )

    score += 30
    reasons.append("homepage_verified")
    if business and business.lower() not in GENERIC_PAGE_TITLES:
        score += 15
        reasons.append("business_name_verified")
    if channel == "email":
        score += 25
        reasons.append("email_available")
    elif channel == "contact_form":
        score += 20
        reasons.append("contact_path_available")
    elif channel == "phone":
        score += 10
        reasons.append("phone_only")
    else:
        reasons.append("no_outreach_channel")
    if offer.confidence == "high":
        score += 20
        reasons.append("strong_audit_evidence")
    elif offer.confidence == "medium":
        score += 12
        reasons.append("usable_audit_evidence")
    source_score = parse_int(row.get("score", ""))
    if source_score >= 70:
        score += 10
        reasons.append("strong_discovery_score")

    if channel == "none" or offer.confidence == "low" or score < 60:
        return LeadQualification("research_required", tuple(reasons), channel, min(score, 100))
    return LeadQualification("ready_for_review", tuple(reasons), channel, min(score, 100))


def outreach_channel(row: dict[str, str], signals: WebsiteSignals) -> str:
    if looks_like_email(row.get("email", "")):
        return "email"
    if row.get("contact_page") or signals.has_contact_path:
        return "contact_form"
    if row.get("phone"):
        return "phone"
    return "none"


def queue_row(
    lead_id: str,
    source_lead_id: str,
    lead: dict[str, str],
    signals: WebsiteSignals,
    offer: OfferMatch,
    qualification: LeadQualification,
    report_path: Path,
) -> dict[str, str | int]:
    return {
        "lead_id": lead_id,
        "source_lead_id": source_lead_id,
        "business_name": lead.get("business_name", ""),
        "contact_name": lead.get("contact_name", ""),
        "website": signals.url,
        "email": lead.get("email", ""),
        "phone": lead.get("phone", ""),
        "outreach_channel": qualification.channel,
        "segment": lead.get("segment", ""),
        "recommended_offer": offer.recommended_offer,
        "price_range": PRICE_RANGES[offer.recommended_offer],
        "specific_observation": offer.specific_observation,
        "evidence_page": signals.evidence_page,
        "page_findings": " ".join(signals.page_findings),
        "funnel_sequence": signals.funnel_sequence,
        "business_reason": offer.business_reason,
        "evidence_url": signals.url,
        "evidence_summary": evidence_summary(signals),
        "what_to_show_on_call": offer.what_to_show_on_call,
        "email_subject": email_subject(lead, offer, signals),
        "meeting_email": meeting_email(lead, offer),
        "call_notes": call_notes(lead, offer),
        "priority_score": max(offer.priority_score, qualification.score),
        "confidence": offer.confidence,
        "qualification_reasons": " | ".join(qualification.reasons),
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "send_status": "needs_review",
        "report_path": str(report_path),
    }


def review_row(
    source_lead_id: str,
    lead: dict[str, str],
    status: str,
    reasons: tuple[str, ...],
    offer: OfferMatch | None = None,
) -> dict[str, str]:
    return {
        "source_lead_id": source_lead_id,
        "business_name": lead.get("business_name", ""),
        "website": site_root_url(lead.get("website", "")),
        "email": lead.get("email", ""),
        "phone": lead.get("phone", ""),
        "qualification_status": status,
        "qualification_reasons": " | ".join(reasons),
        "recommended_offer": offer.recommended_offer if offer else "",
        "confidence": offer.confidence if offer else "",
        "audited_at": datetime.now(timezone.utc).isoformat(),
    }


def render_meeting_report(
    lead: dict[str, str],
    signals: WebsiteSignals,
    offer: OfferMatch,
    queue: dict[str, str | int],
) -> str:
    return "\n".join(
        [
            f"# NexStudio Meeting Brief: {lead.get('business_name') or 'Lead'}",
            "",
            f"Website: {signals.url}",
            f"Recommended offer: {offer.recommended_offer}",
            f"Internal price range: {PRICE_RANGES[offer.recommended_offer]}",
            f"Priority score: {queue['priority_score']}/100",
            f"Confidence: {offer.confidence}",
            "",
            "## Verified Angle",
            "",
            f"- Observation: {offer.specific_observation}",
            f"- Why it matters: {offer.business_reason}",
            f"- Show on call: {offer.what_to_show_on_call}",
            "",
            "## Evidence",
            "",
            f"- Homepage title: {signals.title or 'not found'}",
            f"- Pages found: {', '.join(signals.pages_found) or 'none detected'}",
            f"- Service terms: {', '.join(signals.service_terms) or 'none detected'}",
            f"- Signals: {evidence_summary(signals)}",
            "",
            "## Outreach",
            "",
            f"Subject: {queue['email_subject']}",
            "",
            str(queue["meeting_email"]),
            "",
            "## Call Notes",
            "",
            str(queue["call_notes"]),
            "",
        ]
    )


def meeting_email(lead: dict[str, str], offer: OfferMatch) -> str:
    business = lead.get("business_name") or "your business"
    greeting = greeting_for(lead.get("contact_name", ""))
    return "\n\n".join(
        [
            greeting,
            f"While looking at {possessive(business)} site, I noticed {lower_first(strip_period(offer.specific_observation))}.",
            strip_period(offer.business_reason) + ".",
            f"I can bring {strip_period(offer.what_to_show_on_call)}, then walk you through it in 15 minutes. Would Tuesday or Wednesday work?",
            f"Best,\n{AGENCY_NAME}\n{AGENCY_URL}",
        ]
    )


def email_subject(
    lead: dict[str, str],
    offer: OfferMatch,
    signals: WebsiteSignals | None = None,
) -> str:
    business = lead.get("business_name") or "your site"
    service = primary_service_term(
        lead,
        signals or WebsiteSignals(url="", service_terms=extract_service_terms(lead)),
    )
    if offer.recommended_offer == SERVICE_PAGE_OFFER:
        subject = f"{service} page idea for {business}"
    elif offer.recommended_offer == AUTOMATION_OFFER:
        subject = f"inquiry follow-up at {business}"
    else:
        subject = f"homepage idea for {business}"
    return trim_subject(subject)


def call_notes(lead: dict[str, str], offer: OfferMatch) -> str:
    return (
        f"Open with the verified observation, then show {offer.what_to_show_on_call}. "
        "Ask: Which service is most valuable? How do new enquiries get handled today? What is one new customer worth? "
        f"If the gap is confirmed, scope the {offer.recommended_offer} at {PRICE_RANGES[offer.recommended_offer]}."
    )


def service_page_score(row: dict[str, str], signals: WebsiteSignals) -> int:
    if not signals.service_terms:
        return 10
    score = 20
    if signals.website_service_terms:
        score += 20
    elif signals.service_terms:
        score += 5
    if not signals.has_service_page:
        score += 25
    else:
        score -= 15
    if (
        row.get("segment") == "small_business"
        and not signals.has_location_page
        and (row.get("city") or row.get("category"))
    ):
        score += 10
    if row.get("segment") in {"small_business", "shop_owner", "tutor"}:
        score += 8
    return max(0, min(score, 100))


def conversion_score_for(row: dict[str, str], signals: WebsiteSignals) -> int:
    score = 20
    if not signals.has_cta:
        score += 30
    if not signals.has_proof:
        score += 20
    if not signals.has_booking:
        score += 8
    if parse_int(row.get("maps_reviews", "")) >= 25:
        score += 10
        if not signals.has_cta:
            score += 20
    return max(0, min(score, 100))


def automation_score_for(signals: WebsiteSignals) -> int:
    score = 5
    if signals.has_form:
        score += 25
    elif signals.has_contact_path:
        score += 10
    if not signals.has_chat:
        score += 5
    if signals.has_form and not signals.has_booking:
        score += 15
    if signals.has_booking:
        score -= 20
    return max(0, min(score, 100))


def detect_pages(links: tuple[str, ...]) -> set[str]:
    pages: set[str] = set()
    page_terms = {
        "services": ("service", "treatment", "solution", "procedure"),
        "about": ("about", "team"),
        "contact": ("contact", "get-in-touch"),
        "locations": ("location", "areas-served", "service-area"),
        "faq": ("faq", "frequently"),
        "pricing": ("pricing", "prices", "cost"),
        "case_studies": ("case-study", "case-studies", "portfolio", "results", "reviews"),
    }
    paths = " ".join(urlparse(link).path.lower() for link in links)
    for name, terms in page_terms.items():
        if any(term in paths for term in terms):
            pages.add(name)
    return pages


def extract_service_terms(row: dict[str, str], website_text: str = "") -> tuple[str, ...]:
    source = " ".join(
        [
            website_text,
            row.get("category", ""),
            row.get("source_query", ""),
            row.get("title", ""),
            row.get("business_name", ""),
        ]
    ).lower()
    terms = [raw for raw in SERVICE_TERMS if raw in source]
    if row.get("category") and not terms:
        terms.append(row["category"].lower())
    return tuple(dict.fromkeys(terms))[:6]


def extract_target_service_terms(row: dict[str, str]) -> tuple[str, ...]:
    if row.get("segment") == "coach":
        descriptive_text = " ".join(
            (
                row.get("title", ""),
                row.get("business_name", ""),
                row.get("category", ""),
            )
        ).lower()
        coaching_aliases = (
            ("executive coach", "executive coaching"),
            ("business coach", "business coaching"),
            ("leadership coach", "leadership coaching"),
            ("career coach", "career coaching"),
        )
        for phrase, canonical in coaching_aliases:
            if phrase in descriptive_text:
                return (canonical,)
        return ("coaching",)
    return extract_service_terms({"source_query": row.get("source_query", "")})


def primary_service_term(row: dict[str, str], signals: WebsiteSignals) -> str:
    if signals.service_terms:
        return signals.service_terms[0]
    if row.get("category"):
        return row["category"].lower()
    return "your core service"


def evidence_summary(signals: WebsiteSignals) -> str:
    evidence = [
        f"CTA={'yes' if signals.has_cta else 'no'}",
        f"proof={'yes' if signals.has_proof else 'no'}",
        f"form={'yes' if signals.has_form else 'no'}",
        f"booking={'yes' if signals.has_booking else 'no'}",
        f"chat={'yes' if signals.has_chat else 'no'}",
        f"analytics={'yes' if signals.has_analytics else 'no'}",
    ]
    return "; ".join(evidence)


def is_plausible_site_name(value: str, website: str) -> bool:
    if not value or value.lower() in GENERIC_PAGE_TITLES or len(value) > 65:
        return False
    if re.search(r"^[^,]+,\s*[^,]+$", value):
        return False
    if any(term in value.lower() for term in ("best cosmetic", "near me", "top rated")):
        return False
    domain = domain_key(website).split(".", 1)[0]
    distinctive_tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) >= 3 and token not in GENERIC_BRAND_TOKENS
    ]
    return not distinctive_tokens or any(token in domain for token in distinctive_tokens)


def contains_any(value: str, terms: tuple[str, ...]) -> bool:
    return any(term in value for term in terms)


def term_in_links(term: str, links: tuple[str, ...]) -> bool:
    token = re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-")
    aliases = SERVICE_LINK_ALIASES.get(term.lower(), (token,))
    return any(
        alias and alias in urlparse(link).path.lower()
        for link in links
        for alias in aliases
    )


def looks_like_email(value: str) -> bool:
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value.strip()))


def greeting_for(contact_name: str) -> str:
    first = contact_name.strip().split()[0] if contact_name.strip() else ""
    if first and re.fullmatch(r"[A-Za-z][A-Za-z'-]{1,30}", first):
        return f"Hi {first},"
    return "Hi there,"


def possessive(value: str) -> str:
    return value + "'" if value.lower().endswith("s") else value + "'s"


def trim_subject(value: str, limit: int = 49) -> str:
    if len(value) <= limit:
        return value
    shortened = value[: limit - 1].rsplit(" ", 1)[0].rstrip(" -,:;")
    return shortened or value[:limit]


def strip_period(value: str) -> str:
    return value.strip().rstrip(".")


def lower_first(value: str) -> str:
    if not value:
        return value
    if value.startswith("I "):
        return value
    return value[:1].lower() + value[1:]


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "lead"


def parse_int(value: str) -> int:
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return 0


CTA_TERMS = (
    "book now",
    "book a call",
    "book your call",
    "book your free call",
    "book your free discovery call",
    "book appointment",
    "discovery call",
    "schedule a call",
    "schedule consultation",
    "schedule a consultation",
    "request a quote",
    "get a quote",
    "get started",
    "get in touch",
    "let's work together",
    "enquire now",
    "inquire now",
    "contact us",
    "call now",
)
PROOF_TERMS = (
    "testimonial",
    "case study",
    "case studies",
    "before and after",
    "customer reviews",
    "client reviews",
    "our results",
    "trusted by",
)
PROOF_MARKERS = (
    "testimonial",
    "case-study",
    "case_study",
    "customer-review",
    "client-review",
    "success-story",
)
CONTACT_TERMS = (
    "mailto:",
    "tel:",
    "/contact",
    "contact us",
    "call us",
    "email us",
)
BOOKING_TERMS = (
    "calendly",
    "acuityscheduling",
    "booksy",
    "mindbody",
    "vagaro",
    "janeapp",
    "schedule appointment",
    "schedule a call",
    "discovery call",
    "book a call",
    "book your call",
    "book appointment",
    "book now",
)
CHAT_TERMS = (
    "intercom",
    "drift.com",
    "tawk.to",
    "crisp.chat",
    "tidio",
    "livechat",
    "chatwoot",
    "hubspot-conversations",
    "chatbot",
    "live chat",
)
ANALYTICS_TERMS = (
    "googletagmanager",
    "google-analytics",
    "gtag(",
    "analytics.js",
    "plausible.io",
    "clarity.ms",
    "hotjar",
    "segment.com/analytics",
)
NON_CONTENT_TAGS = {
    "script",
    "style",
    "noscript",
    "template",
    "svg",
}
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
SERVICE_LINK_ALIASES = {
    "executive coaching": ("executive-coaching", "leadership-coaching"),
    "leadership coaching": ("leadership-coaching", "executive-coaching"),
    "business coaching": ("business-coaching", "coaching-services"),
    "career coaching": ("career-coaching", "coaching-services"),
    "coaching": ("coaching",),
}
AGENCY_FORBIDDEN_SERVICE_TERMS = {
    "web design",
    "seo",
}


def element_is_hidden(attrs: dict[str, str]) -> bool:
    class_tokens = set(attrs.get("class", "").lower().split())
    style = re.sub(r"\s+", "", attrs.get("style", "").lower())
    return (
        "hidden" in attrs
        or attrs.get("aria-hidden", "").lower() == "true"
        or bool(class_tokens & {"hide", "hidden", "is-hidden", "w-condition-invisible"})
        or "display:none" in style
        or "visibility:hidden" in style
    )
GENERIC_BRAND_TOKENS = {
    "aesthetic",
    "beauty",
    "care",
    "center",
    "centre",
    "clinic",
    "company",
    "dental",
    "dentist",
    "group",
    "institute",
    "medical",
    "medspa",
    "service",
    "services",
    "spa",
    "studio",
}
SERVICE_TERMS = (
    "dental implants",
    "invisalign",
    "teeth whitening",
    "cosmetic dentistry",
    "dental",
    "botox",
    "dermal fillers",
    "laser hair removal",
    "facial",
    "med spa",
    "personal training",
    "roof repair",
    "roof replacement",
    "emergency roofing",
    "ac repair",
    "hvac installation",
    "emergency hvac",
    "hvac",
    "work visa",
    "citizenship",
    "immigration",
    "executive coaching",
    "business coaching",
    "leadership coaching",
    "career coaching",
    "coaching",
    "web design",
    "seo",
    "branding",
    "interior design",
    "real estate",
    "tutoring",
    "accounting",
    "legal services",
    "consulting",
)
