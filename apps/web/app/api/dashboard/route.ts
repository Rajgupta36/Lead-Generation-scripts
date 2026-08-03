import { prisma } from "@nexstudio/db";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const organizationId = new URL(request.url).searchParams.get("organizationId");
  if (!organizationId) return Response.json({ error: "organizationId is required" }, { status: 400 });
  const [companies, qualified, drafts, sent, replied, runs] = await Promise.all([
    prisma.company.count({ where: { organizationId } }),
    prisma.company.count({ where: { organizationId, leadStatus: { in: ["QUALIFIED", "REVIEW", "APPROVED", "CONTACTED", "REPLIED", "CONVERTED"] } } }),
    prisma.emailSent.count({ where: { status: "DRAFT", contact: { company: { organizationId } } } }),
    prisma.emailSent.count({ where: { status: { in: ["SENT", "DELIVERED", "REPLIED"] }, contact: { company: { organizationId } } } }),
    prisma.emailSent.count({ where: { status: "REPLIED", contact: { company: { organizationId } } } }),
    prisma.apolloSearchRun.findMany({ where: { organizationId }, orderBy: { createdAt: "desc" }, take: 10 })
  ]);
  return Response.json({ totals: { companies, qualified, drafts, sent, replied, replyRate: sent ? replied / sent : 0 }, runs });
}
