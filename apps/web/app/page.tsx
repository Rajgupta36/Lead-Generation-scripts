import { prisma } from "@nexstudio/db";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  let organization: { id: string; name: string } | null = null;
  let databaseError = false;
  let companies = 0;
  let qualified = 0;
  let drafts = 0;
  let sent = 0;
  try {
    organization = await prisma.organization.findUnique({ where: { slug: "nexstudio-local" }, select: { id: true, name: true } });
    const organizationId = organization?.id ?? "";
    if (organizationId) [companies, qualified, drafts, sent] = await Promise.all([
      prisma.company.count({ where: { organizationId } }),
      prisma.company.count({ where: { organizationId, leadStatus: { in: ["QUALIFIED", "REVIEW", "APPROVED", "CONTACTED", "REPLIED", "CONVERTED"] } } }),
      prisma.emailSent.count({ where: { status: "DRAFT", contact: { company: { organizationId } } } }),
      prisma.emailSent.count({ where: { status: { in: ["SENT", "DELIVERED", "REPLIED"] }, contact: { company: { organizationId } } } })
    ]);
  } catch {
    databaseError = true;
  }
  const cards = [["Apollo companies", companies, "All imported companies"], ["Qualified leads", qualified, "After website audit and scoring"], ["Review queue", drafts, "Drafts waiting for approval"], ["Emails sent", sent, "No emails are sent automatically"]];
  return (
    <main style={{ maxWidth: 1180, margin: "0 auto", padding: "72px 28px" }}>
      <p style={{ color: "#8b9cff", letterSpacing: ".12em", textTransform: "uppercase", fontSize: 12 }}>NexStudio / Lead Engine</p>
      <h1 style={{ fontSize: 48, margin: "12px 0", letterSpacing: "-.04em" }}>Apollo-first growth workspace</h1>
      <p style={{ color: "#aab4d1", maxWidth: 640, lineHeight: 1.7 }}>
        Discover targeted companies in Apollo, identify decision makers, audit their websites, and move only qualified opportunities into human-reviewed outreach.
      </p>
      {databaseError && <p style={{ border: "1px solid #7f4b4b", borderRadius: 10, padding: 14, color: "#ffb4b4" }}>Database is not connected. Add a production `DATABASE_URL` in Vercel, then redeploy. Local Docker databases are not reachable from Vercel.</p>}
      <section style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginTop: 42 }}>
        {cards.map(([label, value, detail]) => (
          <article key={label} style={{ border: "1px solid #273252", borderRadius: 14, padding: 20, background: "#11182d" }}>
            <div style={{ color: "#aab4d1", fontSize: 14 }}>{label}</div>
            <div style={{ fontSize: 34, fontWeight: 700, margin: "12px 0 8px" }}>{value}</div>
            <div style={{ color: "#7e8aac", fontSize: 13 }}>{detail}</div>
          </article>
        ))}
      </section>
      <section style={{ marginTop: 36, border: "1px solid #273252", borderRadius: 14, padding: 24, background: "#11182d" }}>
        <h2 style={{ marginTop: 0 }}>Start with an Apollo search</h2>
        <p style={{ color: "#aab4d1", lineHeight: 1.6 }}>The first production slice is intentionally narrow: Apollo search → company record → decision maker → audit → score → draft → review.</p>
        <nav style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
          <a href="/review" style={{ color: "#9daaff" }}>Review drafts →</a>
          <a href="/audits" style={{ color: "#9daaff" }}>Open audit reports →</a>
          <a href="/api/health" style={{ color: "#9daaff" }}>Check service health →</a>
        </nav>
      </section>
      <p style={{ color: "#667394", fontSize: 13, marginTop: 24 }}>Organization: `{organization?.name ?? "not initialized"}`</p>
    </main>
  );
}
