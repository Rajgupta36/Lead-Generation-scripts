import { prisma } from "@nexstudio/db";

export const dynamic = "force-dynamic";

export default async function AuditsPage() {
  const organization = await prisma.organization.findUnique({ where: { slug: "nexstudio-local" } });
  const companies = organization ? await prisma.company.findMany({ where: { organizationId: organization.id }, include: { audits: { orderBy: { createdAt: "desc" }, take: 1 }, scores: { orderBy: { createdAt: "desc" }, take: 1 } }, orderBy: { companyName: "asc" } }) : [];
  return <main style={{ maxWidth: 1200, margin: "0 auto", padding: "48px 28px" }}>
    <a href="/" style={{ color: "#9daaff" }}>← Dashboard</a><h1>Website audit reports</h1>
    <p style={{ color: "#aab4d1" }}>{companies.length} companies audited. Click a company domain to inspect the live site.</p>
    <div style={{ overflowX: "auto" }}><table style={{ width: "100%", borderCollapse: "collapse" }}><thead><tr><th align="left">Company</th><th align="left">Score</th><th align="left">TTFB</th><th align="left">Mobile</th><th align="left">Metadata</th></tr></thead><tbody>
      {companies.map((company) => { const audit = company.audits[0]; const score = company.scores[0]; return <tr key={company.id} style={{ borderTop: "1px solid #273252" }}><td style={{ padding: "14px 8px" }}><a href={`https://${company.domain}`} target="_blank" style={{ color: "#d8def5" }}>{company.companyName}</a><div style={{ color: "#667394", fontSize: 12 }}>{company.domain}</div></td><td>{score?.score ?? "—"}</td><td>{audit?.ttfbMs ? `${audit.ttfbMs} ms` : "—"}</td><td>{audit?.mobileResponsive === undefined ? "—" : audit.mobileResponsive ? "Yes" : "No"}</td><td>{Array.isArray(audit?.missingMetadata) && audit.missingMetadata.length ? audit.missingMetadata.join(", ") : "Complete"}</td></tr>; })}
    </tbody></table></div>
  </main>;
}
