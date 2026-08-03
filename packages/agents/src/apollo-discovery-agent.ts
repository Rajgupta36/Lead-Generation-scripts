import type { ApolloSearchFilters, DiscoveredCompany, LeadProvider } from "@nexstudio/core";

export class ApolloDiscoveryAgent {
  constructor(private readonly provider: LeadProvider) {}

  discover(filters: ApolloSearchFilters): Promise<DiscoveredCompany[]> {
    return this.provider.discoverCompanies(filters);
  }
}
