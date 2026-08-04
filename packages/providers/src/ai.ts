export type CompanyAnalysis = {
  summary: string;
  painPoints: string[];
  recommendedServices: string[];
  estimatedProjectValue: number;
  reasonsToContact: string[];
};

export type EmailDraft = { subject: string; body: string; cta: string };

export type OutreachIdentity = { senderName: string; calLink: string; websiteUrl: string };

const DEFAULT_IDENTITY: OutreachIdentity = {
  senderName: "Raj Gupta",
  calLink: "https://cal.com/nexstudio",
  websiteUrl: "https://www.nexstudio.work/"
};

export class AIProvider {
  private readonly identity: OutreachIdentity;

  constructor(
    private readonly apiKey?: string,
    private readonly fetcher: typeof fetch = fetch,
    identity: Partial<OutreachIdentity> = {}
  ) {
    this.identity = { ...DEFAULT_IDENTITY, ...identity };
  }

  async analyze(input: Record<string, unknown>): Promise<CompanyAnalysis> {
    if (!this.apiKey) return this.fallbackAnalysis(input);
    const content = await this.complete("Return JSON with summary, painPoints, recommendedServices, estimatedProjectValue, reasonsToContact.", input);
    return JSON.parse(content) as CompanyAnalysis;
  }

  async generateEmail(input: Record<string, unknown>): Promise<EmailDraft> {
    if (!this.apiKey) {
      const name = String(input.contactName ?? "there");
      const company = String(input.companyName ?? "your company");
      const { findings, extraCount } = buildFindings(input);
      const { senderName, calLink, websiteUrl } = this.identity;
      const intro =
        findings.length === 0
          ? `I took a quick look at ${company}'s website and spotted a few opportunities worth sharing.`
          : `I took a quick look at ${company}'s website and noticed ${findings.length === 1 ? "one thing" : "a couple of things"}:`;
      const findingsBlock = findings.length ? `\n\n${findings.join("\n")}` : "";
      const extraLine = extraCount > 0 ? `\n\nI spotted a few other opportunities as well.` : "";
      return {
        subject: `${company} website idea`,
        body: `Hi ${name},\n\n${intro}${findingsBlock}${extraLine}\n\nIf you're interested, I'd be happy to record a free 15-minute teardown showing exactly what I'd improve and why.\n\nYou can grab a time here if that's easier:\n${calLink}\n\nBest,\n\n${senderName}\nNexStudio\n${websiteUrl}`,
        cta: "15-minute teardown"
      };
    }
    const content = await this.complete(
      `Write a cold outreach email in this exact structure: "Hi {name}," greeting; one sentence saying you looked at {company}'s website and noticed N things, followed by each finding as its own line ending with why it matters; if there are more findings than shown, add "I spotted a few other opportunities as well."; an offer to record a free 15-minute teardown; a line offering to grab time with the cal link; and a signature block with sender name, "NexStudio", and the website URL. Return JSON with subject, body, cta. Keep it concise and specific, no fluff. Use calLink "${this.identity.calLink}", senderName "${this.identity.senderName}", and websiteUrl "${this.identity.websiteUrl}" exactly as given.`,
      input
    );
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

function buildFindings(input: Record<string, unknown>): { findings: string[]; extraCount: number } {
  const audit = input.audit as { missingMetadata?: string[]; ttfbMs?: number; mobileResponsive?: boolean; hasForms?: boolean } | undefined;
  const all: string[] = [];
  const missingMetadata = audit?.missingMetadata ?? [];
  if (missingMetadata.includes("description")) all.push("The homepage is missing a meta description, which can reduce click-throughs from Google search.");
  if (missingMetadata.includes("viewport")) all.push("The homepage is missing a mobile viewport setting, which can hurt how it renders on phones.");
  if ((audit?.ttfbMs ?? 0) > 1500) all.push(`The initial server response was around ${Math.round((audit?.ttfbMs ?? 0) / 100) / 10} seconds in my test, which may be slowing down the experience for visitors.`);
  if (audit?.mobileResponsive === false) all.push("The homepage doesn't render cleanly on mobile, which can push visitors away before they convert.");
  if (audit?.hasForms === false) all.push("I couldn't find a clear enquiry form on the page I checked, which can cost you leads.");
  const findings = all.slice(0, 2);
  return { findings, extraCount: Math.max(0, all.length - findings.length) };
}
