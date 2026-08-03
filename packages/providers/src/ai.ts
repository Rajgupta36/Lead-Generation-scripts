export type CompanyAnalysis = {
  summary: string;
  painPoints: string[];
  recommendedServices: string[];
  estimatedProjectValue: number;
  reasonsToContact: string[];
};

export type EmailDraft = { subject: string; body: string; cta: string };

export class AIProvider {
  constructor(private readonly apiKey?: string, private readonly fetcher: typeof fetch = fetch) {}

  async analyze(input: Record<string, unknown>): Promise<CompanyAnalysis> {
    if (!this.apiKey) return this.fallbackAnalysis(input);
    const content = await this.complete("Return JSON with summary, painPoints, recommendedServices, estimatedProjectValue, reasonsToContact.", input);
    return JSON.parse(content) as CompanyAnalysis;
  }

  async generateEmail(input: Record<string, unknown>): Promise<EmailDraft> {
    if (!this.apiKey) {
      const name = String(input.contactName ?? "there");
      const company = String(input.companyName ?? "your company");
      const evidence = buildEvidence(input);
      return {
        subject: `${company} website idea`,
        body: `Hi ${name},\n\nI took a quick look at ${company}'s website. ${evidence}\n\nNexStudio helps service businesses turn website friction into more qualified enquiries. Would a 15-minute teardown be useful next week?`,
        cta: "15-minute teardown"
      };
    }
    const content = await this.complete("Return JSON with subject, body, cta. Write concise, specific cold outreach without fluff.", input);
    return JSON.parse(content) as EmailDraft;
  }

  private async complete(instruction: string, input: Record<string, unknown>): Promise<string> {
    const response = await this.fetcher("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${this.apiKey}` },
      body: JSON.stringify({ model: "gpt-4o-mini", temperature: 0.3, response_format: { type: "json_object" }, messages: [
        { role: "system", content: instruction },
        { role: "user", content: JSON.stringify(input) }
      ] })
    });
    if (!response.ok) throw new Error(`AI request failed with ${response.status}`);
    const json = await response.json() as { choices?: Array<{ message?: { content?: string } }> };
    const content = json.choices?.[0]?.message?.content;
    if (!content) throw new Error("AI returned no content");
    return content;
  }

  private fallbackAnalysis(input: Record<string, unknown>): CompanyAnalysis {
    const audit = input.audit as { missingMetadata?: string[]; ttfbMs?: number; mobileResponsive?: boolean } | undefined;
    const painPoints = [
      ...((audit?.missingMetadata ?? []).includes("description") ? ["The homepage is missing a meta description"] : []),
      ...((audit?.missingMetadata ?? []).includes("viewport") ? ["The homepage is missing a mobile viewport setting"] : []),
      ...((audit?.ttfbMs ?? 0) > 1500 ? ["The website has a slow initial server response"] : []),
      ...(audit?.mobileResponsive === false ? ["The homepage needs a mobile rendering review"] : [])
    ];
    return { summary: `${String(input.companyName ?? "The company")} has a qualified Apollo profile and a website opportunity worth reviewing.`, painPoints, recommendedServices: ["Website strategy", "Conversion-focused redesign", "Performance optimization"], estimatedProjectValue: 5000, reasonsToContact: painPoints.length ? painPoints : ["A specific website teardown can create a useful starting point"] };
  }
}

function buildEvidence(input: Record<string, unknown>): string {
  const audit = input.audit as { missingMetadata?: string[]; ttfbMs?: number; mobileResponsive?: boolean; hasForms?: boolean } | undefined;
  const findings: string[] = [];
  const missingMetadata = audit?.missingMetadata ?? [];
  if (missingMetadata.includes("description")) findings.push("the homepage does not appear to have a meta description, so its search snippet may be less useful");
  if ((audit?.ttfbMs ?? 0) > 1500) findings.push(`the site took roughly ${Math.round((audit?.ttfbMs ?? 0) / 100) / 10} seconds to start responding in my check`);
  if (audit?.mobileResponsive === false) findings.push("the homepage needs a closer mobile rendering review");
  if (audit?.hasForms === false) findings.push("I could not find a clear enquiry form on the page I checked");
  if (findings.length === 0) return String(input.reason ?? "a few practical website opportunities");
  if (findings.length === 1) return `I noticed ${findings[0]}.`;
  return `Two things stood out: ${findings.slice(0, 2).join("; ")}.`;
}
