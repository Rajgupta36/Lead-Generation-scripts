import { LeadStatus, VerificationStatus, EmailStatus, Prisma } from "@prisma/client";
import { getEnv, isGenericEmail, scoreLead, type ApolloSearchFilters } from "@nexstudio/core";
import { prisma } from "@nexstudio/db";
import { logger } from "@nexstudio/observability";
import { ApolloProvider, AIProvider, ResendEmailSender, WebsiteAuditProvider } from "@nexstudio/providers";
import { enqueueFollowup } from "@nexstudio/queues";
import { enqueueEmailGeneration, enqueueLeadScore, enqueueWebsiteAudit } from "@nexstudio/queues";

export class ApolloPipelineService {
  private readonly apollo: ApolloProvider | undefined;
  private readonly ai: AIProvider;
  private readonly auditor: WebsiteAuditProvider;

  constructor() {
    const env = getEnv();
    this.apollo = env.APOLLO_API_KEY ? new ApolloProvider({ apiKey: env.APOLLO_API_KEY, baseUrl: env.APOLLO_BASE_URL }) : undefined;
    this.ai = new AIProvider(env.OPENAI_API_KEY);
    this.auditor = new WebsiteAuditProvider();
  }

  async discover(organizationId: string, runId: string, filters: ApolloSearchFilters): Promise<number> {
    if (!this.apollo) throw new Error("Apollo API is disabled. Import an Apollo CSV or configure APOLLO_API_KEY.");
    const run = await prisma.apolloSearchRun.findFirst({ where: { id: runId, organizationId } });
    if (!run) throw new Error("Apollo search run not found");
    await prisma.apolloSearchRun.update({ where: { id: run.id }, data: { status: "running" } });
    try {
      const companies = await this.apollo.discoverCompanies(filters);
      for (const company of companies) {
        const persisted = await prisma.company.upsert({
          where: { organizationId_domain: { organizationId, domain: company.domain } },
          create: { organizationId, domain: company.domain, companyName: company.companyName, industry: company.industry ?? null, employees: company.employees ?? null, location: company.location ?? null, linkedinUrl: company.linkedinUrl ?? null },
          update: { companyName: company.companyName, industry: company.industry ?? null, employees: company.employees ?? null, location: company.location ?? null, linkedinUrl: company.linkedinUrl ?? null }
        });
        await prisma.apolloCompany.upsert({ where: { runId_companyId: { runId, companyId: persisted.id } }, create: { runId, companyId: persisted.id, sourceId: company.sourceRecordId ?? null, payload: company }, update: { payload: company, sourceId: company.sourceRecordId ?? null } });
        const contacts = await this.apollo.discoverContacts(company.domain);
        for (const contact of contacts) {
          await prisma.contact.upsert({
            where: { id: `${persisted.id}:${contact.fullName}` },
            create: { id: `${persisted.id}:${contact.fullName}`, companyId: persisted.id, fullName: contact.fullName, role: contact.role, linkedinUrl: contact.linkedinUrl ?? null, email: contact.email ?? null, verificationStatus: VerificationStatus.UNKNOWN, confidence: contact.confidence, source: contact.source },
            update: { role: contact.role, linkedinUrl: contact.linkedinUrl ?? null, email: contact.email ?? null, confidence: contact.confidence }
          });
        }
        await enqueueWebsiteAudit({ companyId: persisted.id, url: `https://${company.domain}` });
      }
      await prisma.apolloSearchRun.update({ where: { id: run.id }, data: { status: "completed", resultCount: companies.length } });
      return companies.length;
    } catch (error) {
      await prisma.apolloSearchRun.update({ where: { id: run.id }, data: { status: "failed" } });
      throw error;
    }
  }

  async importCsv(organizationId: string, runId: string, csv: string): Promise<number> {
    const run = await prisma.apolloSearchRun.findFirst({ where: { id: runId, organizationId } });
    if (!run) throw new Error("Apollo search run not found");
    const rows = parseCsv(csv);
    for (const row of rows) {
      if (!row.domain || !row.companyName) continue;
      const domain = normalizeDomain(row.domain);
      const company = await prisma.company.upsert({
        where: { organizationId_domain: { organizationId, domain } },
        create: { organizationId, domain, companyName: row.companyName, industry: row.industry ?? null, employees: row.employees ? Number(row.employees) : null, location: row.location ?? null, linkedinUrl: row.linkedin ?? null },
        update: { companyName: row.companyName, industry: row.industry ?? null, employees: row.employees ? Number(row.employees) : null, location: row.location ?? null, linkedinUrl: row.linkedin ?? null }
      });
      await prisma.apolloCompany.upsert({ where: { runId_companyId: { runId, companyId: company.id } }, create: { runId, companyId: company.id, sourceId: row.apolloId ?? null, payload: row }, update: { payload: row, sourceId: row.apolloId ?? null } });
      if (row.fullName && row.role) {
        await prisma.contact.upsert({ where: { id: `${company.id}:${row.fullName}` }, create: { id: `${company.id}:${row.fullName}`, companyId: company.id, fullName: row.fullName, role: row.role, linkedinUrl: row.linkedin ?? null, email: row.email ?? null, verificationStatus: row.verificationStatus === "verified" ? VerificationStatus.VALID : VerificationStatus.UNKNOWN, confidence: row.email ? 80 : 50, source: "apollo_csv" }, update: { role: row.role, linkedinUrl: row.linkedin ?? null, email: row.email ?? null, confidence: row.email ? 80 : 50 } });
      }
      await enqueueWebsiteAudit({ companyId: company.id, url: `https://${domain}` });
    }
    await prisma.apolloSearchRun.update({ where: { id: run.id }, data: { status: "completed", resultCount: rows.length } });
    return rows.length;
  }

  async audit(companyId: string, url: string): Promise<void> {
    const result = await this.auditor.audit(url);
    await prisma.websiteAudit.create({ data: { companyId, url: result.url, ttfbMs: result.ttfbMs ?? null, brokenLinks: result.brokenLinks, missingMetadata: result.missingMetadata, hasForms: result.hasForms, hasBlog: result.hasBlog, mobileResponsive: result.mobileResponsive, cookieBanner: result.cookieBanner, raw: result.raw as Prisma.InputJsonObject } });
    await enqueueLeadScore({ companyId });
  }

  async score(companyId: string): Promise<number> {
    const [company, audit, contact] = await Promise.all([
      prisma.company.findUniqueOrThrow({ where: { id: companyId } }),
      prisma.websiteAudit.findFirst({ where: { companyId }, orderBy: { createdAt: "desc" } }),
      prisma.contact.findFirst({ where: { companyId }, orderBy: { confidence: "desc" } })
    ]);
    const factors = { outdatedWebsite: Boolean(audit?.missingMetadata && Array.isArray(audit.missingMetadata) && audit.missingMetadata.length > 0), poorPerformance: (audit?.ttfbMs ?? 0) > 1500, activeBlog: audit?.hasBlog === true, verifiedFounderEmail: contact?.verificationStatus === VerificationStatus.VALID };
    const score = scoreLead(factors);
    await prisma.leadScore.create({ data: { companyId, score, factors, rationale: Object.entries(factors).filter(([, value]) => value).map(([key]) => key).join(", ") } });
    await prisma.company.update({ where: { id: companyId }, data: { leadStatus: score >= 40 ? LeadStatus.REVIEW : LeadStatus.QUALIFIED } });
    if (contact && score >= 40) await enqueueEmailGeneration({ contactId: contact.id, sequenceId: "default" });
    return score;
  }

  async generateEmail(contactId: string, sequenceId: string): Promise<string> {
    const contact = await prisma.contact.findUniqueOrThrow({ where: { id: contactId }, include: { company: { include: { audits: { orderBy: { createdAt: "desc" }, take: 1 } } } } });
    if (!contact.email || isGenericEmail(contact.email)) throw new Error("Contact email requires explicit approval before outreach");
    const audit = contact.company.audits[0];
    const analysis = await this.ai.analyze({ companyName: contact.company.companyName, audit });
    const draft = await this.ai.generateEmail({ companyName: contact.company.companyName, contactName: contact.fullName.split(" ")[0], audit, reason: analysis.reasonsToContact[0] });
    const email = await prisma.emailSent.create({ data: { contactId, sequenceId: sequenceId === "default" ? null : sequenceId, subject: draft.subject, body: draft.body, status: EmailStatus.DRAFT } });
    await prisma.company.update({ where: { id: contact.companyId }, data: { aiSummary: analysis.summary, aiPainPoints: analysis.painPoints, recommendedServices: analysis.recommendedServices, estimatedProjectValue: analysis.estimatedProjectValue, reasonsToContact: analysis.reasonsToContact } });
    logger.info("Email draft created", { emailId: email.id, contactId });
    return email.id;
  }

  async regenerateDraft(emailId: string): Promise<void> {
    const email = await prisma.emailSent.findUniqueOrThrow({ where: { id: emailId }, include: { contact: { include: { company: { include: { audits: { orderBy: { createdAt: "desc" }, take: 1 } } } } } } });
    if (email.status !== EmailStatus.DRAFT || !email.contact.email || isGenericEmail(email.contact.email)) return;
    const audit = email.contact.company.audits[0];
    const analysis = await this.ai.analyze({ companyName: email.contact.company.companyName, audit });
    const draft = await this.ai.generateEmail({ companyName: email.contact.company.companyName, contactName: email.contact.fullName.split(" ")[0], audit, reason: analysis.reasonsToContact[0] });
    await prisma.emailSent.update({ where: { id: emailId }, data: { subject: draft.subject, body: draft.body } });
    await prisma.company.update({ where: { id: email.contact.companyId }, data: { aiSummary: analysis.summary, aiPainPoints: analysis.painPoints, recommendedServices: analysis.recommendedServices, estimatedProjectValue: analysis.estimatedProjectValue, reasonsToContact: analysis.reasonsToContact } });
  }

  async sendEmail(emailId: string): Promise<string> {
    const env = getEnv();
    if (!env.RESEND_API_KEY || !env.OUTREACH_FROM_EMAIL) throw new Error("RESEND_API_KEY and OUTREACH_FROM_EMAIL are required");
    const email = await prisma.emailSent.findUniqueOrThrow({ where: { id: emailId }, include: { contact: true } });
    if (!email.contact.email || email.contact.verificationStatus !== VerificationStatus.VALID || isGenericEmail(email.contact.email)) throw new Error("Only verified, non-generic contact emails can be sent");
    const sender = new ResendEmailSender(env.RESEND_API_KEY);
    const result = await sender.send({ to: email.contact.email, subject: email.subject, html: email.body.replaceAll("\n", "<br />"), from: env.OUTREACH_FROM_EMAIL });
    await prisma.emailSent.update({ where: { id: emailId }, data: { status: EmailStatus.SENT, providerId: result.providerId, sentAt: new Date() } });
    await prisma.emailEvent.create({ data: { emailId, type: "sent", providerId: result.providerId } });
    await enqueueFollowup({ emailId, step: 1 }, 3 * 24 * 60 * 60 * 1000);
    return result.providerId;
  }

  async followup(emailId: string, step: number): Promise<void> {
    const email = await prisma.emailSent.findUniqueOrThrow({ where: { id: emailId }, include: { contact: true } });
    if (([EmailStatus.REPLIED, EmailStatus.BOUNCED, EmailStatus.UNSUBSCRIBED] as EmailStatus[]).includes(email.status)) return;
    await prisma.emailEvent.create({ data: { emailId, type: `followup_${step}` } });
    logger.info("Follow-up is ready for review", { emailId, step });
  }
}

function normalizeDomain(value: string): string {
  return value.trim().replace(/^https?:\/\//i, "").replace(/^www\./i, "").replace(/\/.*$/, "").toLowerCase();
}

type CsvRow = { [key: string]: string | undefined; domain?: string; companyName?: string; industry?: string; employees?: string; location?: string; linkedin?: string; fullName?: string; role?: string; email?: string; verificationStatus?: string; apolloId?: string };

function parseCsv(input: string): CsvRow[] {
  const records: string[][] = [];
  let row: string[] = [];
  let value = "";
  let quoted = false;
  for (let index = 0; index < input.length; index += 1) {
    const character = input[index];
    const next = input[index + 1];
    if (character === '"' && quoted && next === '"') { value += '"'; index += 1; continue; }
    if (character === '"') { quoted = !quoted; continue; }
    if (character === "," && !quoted) { row.push(value.trim()); value = ""; continue; }
    if ((character === "\n" || character === "\r") && !quoted) { if (character === "\r" && next === "\n") index += 1; row.push(value.trim()); records.push(row); row = []; value = ""; continue; }
    value += character;
  }
  if (value || row.length) { row.push(value.trim()); records.push(row); }
  const headers = records.shift()?.map((header) => header.toLowerCase().trim().replaceAll(" ", "_")) ?? [];
    return records.filter((record) => record.some(Boolean)).map((record) => {
    const source = Object.fromEntries(headers.map((header, index) => [header, record[index] ?? ""]));
    const firstName = source.first_name || "";
    const lastName = source.last_name || "";
    return { ...source, domain: source.domain || source.website || source.company_domain || source.company_website || source.account_website || "", companyName: source.company_name || source.organization_name || source.account_name || "", fullName: source.full_name || source.name || `${firstName} ${lastName}`.trim(), role: source.role || source.title || "", linkedin: source.linkedin || source.linkedin_url || "", verificationStatus: source.verification_status || source.email_status || "", employees: source.employees || source["#_employees"] || "", apolloId: source.apollo_id || source.person_id || "" };
  });
}
