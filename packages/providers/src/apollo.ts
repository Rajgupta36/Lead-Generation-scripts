import type { ApolloSearchFilters, DiscoveredCompany, DiscoveredContact, LeadProvider } from "@nexstudio/core";

type ApolloClientOptions = {
  apiKey: string;
  baseUrl?: string;
  fetcher?: typeof fetch;
};

type ApolloOrganization = {
  id?: string;
  name?: string;
  primary_domain?: string;
  industry?: string;
  estimated_num_employees?: number;
  city?: string;
  state?: string;
  country?: string;
  linkedin_url?: string;
};

type ApolloPerson = {
  id?: string;
  name?: string;
  title?: string;
  linkedin_url?: string;
  email?: string;
  organization?: ApolloOrganization;
};

export class ApolloProvider implements LeadProvider {
  private readonly fetcher: typeof fetch;
  private readonly baseUrl: string;

  constructor(private readonly options: ApolloClientOptions) {
    this.fetcher = options.fetcher ?? fetch;
    this.baseUrl = options.baseUrl ?? "https://api.apollo.io";
  }

  async discoverCompanies(filters: ApolloSearchFilters): Promise<DiscoveredCompany[]> {
    const response = await this.request<{ organizations?: ApolloOrganization[] }>("/api/v1/mixed_companies/search", {
      q_organization_keyword_tags: filters.keywords,
      organization_num_employees_ranges: filters.employeeRanges,
      organization_locations: filters.locations,
      page: filters.page ?? 1,
      per_page: filters.perPage ?? 25
    });

    return (response.organizations ?? []).flatMap((organization) => {
      if (!organization.primary_domain || !organization.name) return [];
      return [{
        domain: organization.primary_domain,
        companyName: organization.name,
        sourceRunId: "apollo-api",
        ...(organization.industry ? { industry: organization.industry } : {}),
        ...(organization.estimated_num_employees ? { employees: organization.estimated_num_employees } : {}),
        ...([organization.city, organization.state, organization.country].filter(Boolean).join(", ") ? { location: [organization.city, organization.state, organization.country].filter(Boolean).join(", ") } : {}),
        ...(organization.linkedin_url ? { linkedinUrl: organization.linkedin_url } : {}),
        ...(organization.id ? { sourceRecordId: organization.id } : {})
      }];
    });
  }

  async discoverContacts(companyDomain: string): Promise<DiscoveredContact[]> {
    const response = await this.request<{ people?: ApolloPerson[] }>("/api/v1/mixed_people/api_search", {
      q_organization_domains_list: [companyDomain],
      person_titles: ["Founder", "CEO", "Owner", "CTO", "Head of Marketing", "Growth Lead", "Medical Director"],
      per_page: 25
    });

    return (response.people ?? []).flatMap((person) => {
      if (!person.name || !person.title) return [];
      return [{
        companyDomain,
        fullName: person.name,
        role: person.title,
        verificationStatus: person.email ? "unknown" as const : "unknown" as const,
        confidence: person.email ? 80 : 60,
        source: "apollo" as const,
        ...(person.linkedin_url ? { linkedinUrl: person.linkedin_url } : {}),
        ...(person.email ? { email: person.email } : {})
      }];
    });
  }

  private async request<T>(path: string, body: Record<string, unknown>): Promise<T> {
    const response = await this.fetcher(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Cache-Control": "no-cache", "x-api-key": this.options.apiKey },
      body: JSON.stringify(body)
    });
    if (!response.ok) throw new Error(`Apollo request failed with ${response.status}`);
    return response.json() as Promise<T>;
  }
}
