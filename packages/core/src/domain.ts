export type ApolloSearchFilters = {
  titles?: string[];
  locations?: string[];
  industries?: string[];
  employeeRanges?: string[];
  keywords?: string[];
  page?: number;
  perPage?: number;
};

export type DiscoveredCompany = {
  domain: string;
  companyName: string;
  industry?: string;
  employees?: number;
  location?: string;
  linkedinUrl?: string;
  sourceRunId: string;
  sourceRecordId?: string;
};

export type DiscoveredContact = {
  companyDomain: string;
  fullName: string;
  role: string;
  linkedinUrl?: string;
  email?: string;
  verificationStatus: "unknown" | "valid" | "invalid" | "risky";
  confidence: number;
  source: "apollo" | "public_page" | "manual";
};

export type LeadProvider = {
  discoverCompanies(filters: ApolloSearchFilters): Promise<DiscoveredCompany[]>;
  discoverContacts(companyDomain: string): Promise<DiscoveredContact[]>;
};

export const blockedGenericEmailPrefixes = [
  "info",
  "support",
  "sales",
  "contact",
  "hello"
] as const;

export function isGenericEmail(email: string): boolean {
  const prefix = email.split("@", 1)[0]?.toLowerCase();
  return blockedGenericEmailPrefixes.includes(prefix as (typeof blockedGenericEmailPrefixes)[number]);
}

export function scoreLead(factors: {
  outdatedWebsite?: boolean;
  poorPerformance?: boolean;
  hiringEngineers?: boolean;
  recentlyFunded?: boolean;
  activeBlog?: boolean;
  legacyCms?: boolean;
  verifiedFounderEmail?: boolean;
}): number {
  return (
    (factors.outdatedWebsite ? 25 : 0) +
    (factors.poorPerformance ? 20 : 0) +
    (factors.hiringEngineers ? 20 : 0) +
    (factors.recentlyFunded ? 15 : 0) +
    (factors.activeBlog ? 15 : 0) +
    (factors.legacyCms ? 10 : 0) +
    (factors.verifiedFounderEmail ? 30 : 0)
  );
}
