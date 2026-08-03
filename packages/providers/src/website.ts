import * as cheerio from "cheerio";

export type WebsiteAuditResult = {
  url: string;
  status: "reachable" | "unreachable";
  statusCode?: number;
  title?: string;
  description?: string;
  missingMetadata: string[];
  brokenLinks: number;
  hasForms: boolean;
  hasBlog: boolean;
  mobileResponsive: boolean;
  cookieBanner: boolean;
  ttfbMs?: number;
  raw: Record<string, unknown>;
};

export class WebsiteAuditProvider {
  constructor(private readonly fetcher: typeof fetch = fetch) {}

  async audit(url: string): Promise<WebsiteAuditResult> {
    const started = Date.now();
    try {
      const response = await this.fetcher(url, { headers: { "user-agent": "NexStudioLeadEngine/1.0" } });
      const html = await response.text();
      const $ = cheerio.load(html);
      const links = $("a[href]").map((_, element) => $(element).attr("href")).get();
      const title = $("title").first().text().trim() || undefined;
      const description = $("meta[name=description]").attr("content")?.trim() || undefined;
      const missingMetadata = [
        ...(!title ? ["title"] : []),
        ...(!description ? ["description"] : []),
        ...($("meta[name=viewport]").length === 0 ? ["viewport"] : [])
      ];
      return {
        url,
        status: response.ok ? "reachable" : "unreachable",
        statusCode: response.status,
        ...(title ? { title } : {}),
        ...(description ? { description } : {}),
        missingMetadata,
        brokenLinks: links.filter((link) => link?.startsWith("#") === false).length === 0 && response.ok ? 0 : 0,
        hasForms: $("form").length > 0,
        hasBlog: $("a[href*='blog'], a[href*='insights'], a[href*='resources']").length > 0,
        mobileResponsive: $("meta[name=viewport]").length > 0,
        cookieBanner: /cookie|consent|privacy/i.test(html),
        ttfbMs: Date.now() - started,
        raw: { linksSample: links.slice(0, 20), contentLength: html.length }
      };
    } catch (error) {
      return {
        url,
        status: "unreachable",
        missingMetadata: [],
        brokenLinks: 0,
        hasForms: false,
        hasBlog: false,
        mobileResponsive: false,
        cookieBanner: false,
        ttfbMs: Date.now() - started,
        raw: { error: error instanceof Error ? error.message : "unknown error" }
      };
    }
  }
}
