import { prisma } from "@nexstudio/db";
import { ReviewActions } from "./ReviewActions";

export const dynamic = "force-dynamic";

export default async function ReviewPage() {
  const organization = await prisma.organization.findUnique({ where: { slug: "nexstudio-local" } });
  const drafts = organization ? await prisma.emailSent.findMany({ where: { status: "DRAFT", contact: { company: { organizationId: organization.id } } }, include: { contact: { include: { company: true } } }, orderBy: { createdAt: "desc" } }) : [];
  return <main style={{ maxWidth: 1000, margin: "0 auto", padding: "48px 28px" }}>
    <a href="/" style={{ color: "#9daaff" }}>← Dashboard</a>
    <h1>Message review queue</h1>
    <p style={{ color: "#aab4d1" }}>{drafts.length} personalised drafts. Nothing is sent until you approve it.</p>
    {drafts.map((draft) => <article key={draft.id} style={{ border: "1px solid #273252", borderRadius: 14, padding: 24, margin: "18px 0", background: "#11182d" }}>
      <div style={{ color: "#9daaff", fontSize: 13 }}>{draft.contact.company.companyName} · {draft.contact.fullName} · {draft.contact.email}</div>
      <h2 style={{ fontSize: 20 }}>{draft.subject}</h2>
      <pre style={{ whiteSpace: "pre-wrap", font: "inherit", color: "#d8def5", lineHeight: 1.7 }}>{draft.body}</pre>
      <div style={{ color: "#667394", fontSize: 12, marginBottom: 16 }}>Status: {draft.status} · Draft ID: {draft.id}</div>
      <ReviewActions emailId={draft.id} />
    </article>)}
  </main>;
}
