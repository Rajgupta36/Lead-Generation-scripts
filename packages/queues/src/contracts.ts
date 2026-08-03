import type { ApolloSearchFilters } from "@nexstudio/core";

export const queueNames = {
  discovery: "lead-discovery",
  research: "lead-research",
  outreach: "lead-outreach",
  followups: "lead-followups"
} as const;

export type ApolloDiscoveryJob = {
  organizationId: string;
  runId: string;
  filters: ApolloSearchFilters;
};
export type ApolloCsvImportJob = { organizationId: string; runId: string; csv: string };

export type WebsiteAuditJob = { companyId: string; url: string };
export type EmailGenerationJob = { contactId: string; sequenceId: string };
export type ScoreLeadJob = { companyId: string };
export type SendEmailJob = { emailId: string };
export type FollowupJob = { emailId: string; step: number };

export type QueueJobMap = {
  "discover-apollo-companies": ApolloDiscoveryJob;
  "import-apollo-csv": ApolloCsvImportJob;
  "audit-website": WebsiteAuditJob;
  "generate-email": EmailGenerationJob;
  "score-lead": ScoreLeadJob;
  "send-email": SendEmailJob;
  "follow-up": FollowupJob;
};
