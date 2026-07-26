from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from .models import Lead
from .urltools import domain_key


APOLLO_BASE_URL = "https://api.apollo.io/api/v1"


class ApolloClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("APOLLO_API_KEY", "")
        if not self.api_key:
            raise ValueError("APOLLO_API_KEY is required for Apollo enrichment")

    def enrich_lead(
        self,
        lead: Lead,
        include_people: bool = False,
        reveal_personal_emails: bool = False,
        reveal_phone_number: bool = False,
        webhook_url: str = "",
    ) -> Lead:
        domain = domain_key(lead.website)
        if not domain:
            lead.enrichment_provider = "apollo"
            lead.enrichment_status = "skipped_no_domain"
            return lead

        organization = self.enrich_organization(lead, domain)
        apply_organization_enrichment(lead, organization)

        if not include_people:
            lead.enrichment_provider = "apollo"
            return lead

        person = self.find_best_person(domain)
        if person:
            enriched_person = self.enrich_person(
                person,
                lead,
                domain,
                reveal_personal_emails=reveal_personal_emails,
                reveal_phone_number=reveal_phone_number,
                webhook_url=webhook_url,
            )
            apply_person_enrichment(lead, enriched_person or person)

        if lead.enrichment_status == "not_configured":
            lead.enrichment_status = "no_match"
        lead.enrichment_provider = "apollo"
        return lead

    def enrich_organization(self, lead: Lead, domain: str) -> dict:
        params = {
            "domain": domain,
            "website": lead.website,
            "name": lead.business_name,
        }
        return self._get("/organizations/enrich", params)

    def find_best_person(self, domain: str) -> dict:
        payload = {
            "q_organization_domains_list": [domain],
            "person_seniorities": ["owner", "founder", "c_suite", "partner"],
            "person_titles": [
                "founder",
                "owner",
                "co-founder",
                "chief executive officer",
                "ceo",
                "managing partner",
                "principal",
            ],
            "include_similar_titles": True,
            "contact_email_status": ["verified", "likely to engage"],
            "page": 1,
            "per_page": 3,
        }
        data = self._post("/mixed_people/api_search", payload)
        people = data.get("people") or data.get("contacts") or []
        return people[0] if people else {}

    def enrich_person(
        self,
        person: dict,
        lead: Lead,
        domain: str,
        reveal_personal_emails: bool,
        reveal_phone_number: bool,
        webhook_url: str,
    ) -> dict:
        payload = {
            "id": person.get("id") or person.get("person_id"),
            "name": person.get("name"),
            "domain": domain,
            "organization_name": lead.business_name,
            "linkedin_url": person.get("linkedin_url"),
            "reveal_personal_emails": reveal_personal_emails,
            "reveal_phone_number": reveal_phone_number,
        }
        if reveal_phone_number:
            payload["webhook_url"] = webhook_url or os.environ.get("APOLLO_WEBHOOK_URL", "")
        clean_payload = {key: value for key, value in payload.items() if value not in {"", None}}
        return self._post("/people/match", clean_payload)

    def _get(self, path: str, params: dict[str, object]) -> dict:
        clean_params = {key: value for key, value in params.items() if value not in {"", None}}
        url = f"{APOLLO_BASE_URL}{path}?{urllib.parse.urlencode(clean_params)}"
        request = urllib.request.Request(url, headers=self._headers())
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8") or "{}")

    def _post(self, path: str, payload: dict[str, object]) -> dict:
        request = urllib.request.Request(
            f"{APOLLO_BASE_URL}{path}",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={**self._headers(), "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8") or "{}")

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "x-api-key": self.api_key,
        }


def enrich_with_apollo(
    leads: list[Lead],
    max_leads: int | None = None,
    include_people: bool = False,
    reveal_personal_emails: bool = False,
    reveal_phone_number: bool = False,
    webhook_url: str = "",
) -> list[Lead]:
    client = ApolloClient()
    selected = leads if max_leads is None else leads[:max_leads]
    for lead in selected:
        client.enrich_lead(
            lead,
            include_people=include_people,
            reveal_personal_emails=reveal_personal_emails,
            reveal_phone_number=reveal_phone_number,
            webhook_url=webhook_url,
        )
    return leads


def apply_organization_enrichment(lead: Lead, data: dict) -> None:
    organization = data.get("organization") or data.get("account") or data
    if not isinstance(organization, dict) or not organization:
        return
    lead.apollo_organization_id = str(organization.get("id") or lead.apollo_organization_id)
    lead.apollo_employee_count = stringify_first(
        organization.get("estimated_num_employees"),
        organization.get("employee_count"),
        lead.apollo_employee_count,
    )
    lead.apollo_industry = stringify_first(organization.get("industry"), lead.apollo_industry)
    lead.apollo_revenue = stringify_first(organization.get("annual_revenue"), lead.apollo_revenue)
    lead.apollo_company_phone = stringify_first(
        organization.get("phone"),
        organization.get("primary_phone", {}).get("number") if isinstance(organization.get("primary_phone"), dict) else "",
        lead.apollo_company_phone,
    )
    if not lead.phone and lead.apollo_company_phone:
        lead.phone = lead.apollo_company_phone
    if not lead.address:
        lead.address = stringify_first(
            organization.get("raw_address"),
            organization.get("street_address"),
            organization.get("city"),
            lead.address,
        )
    lead.enrichment_status = "organization_enriched"


def apply_person_enrichment(lead: Lead, data: dict) -> None:
    person = data.get("person") or data.get("contact") or data
    if not isinstance(person, dict) or not person:
        return
    lead.apollo_person_id = str(person.get("id") or person.get("person_id") or lead.apollo_person_id)
    lead.apollo_email_status = stringify_first(person.get("email_status"), lead.apollo_email_status)
    lead.contact_name = stringify_first(person.get("name"), lead.contact_name)
    lead.title = stringify_first(person.get("title"), lead.title)
    lead.linkedin = stringify_first(person.get("linkedin_url"), lead.linkedin)
    email = stringify_first(
        person.get("email"),
        first_list_value(person.get("personal_emails")),
        first_list_value(person.get("emails")),
        "",
    )
    if email:
        lead.email = email
    phone = stringify_first(
        person.get("phone_number"),
        person.get("mobile_phone"),
        person.get("sanitized_phone"),
        first_list_value(person.get("phone_numbers")),
        "",
    )
    if phone:
        lead.phone = phone
    if lead.apollo_email_status:
        lead.email_validation_status = lead.apollo_email_status
    lead.enrichment_status = "person_enriched"


def stringify_first(*values: object) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def first_list_value(value: object) -> str:
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict):
            return stringify_first(first.get("email"), first.get("number"), first.get("value"))
        return stringify_first(first)
    return ""
