import { z } from "zod";
import { prisma } from "@nexstudio/db";
import { enqueueSendEmail } from "@nexstudio/queues";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const organizationId = new URL(request.url).searchParams.get("organizationId");
  if (!organizationId) return Response.json({ error: "organizationId is required" }, { status: 400 });
  const drafts = await prisma.emailSent.findMany({ where: { status: "DRAFT", contact: { company: { organizationId } } }, include: { contact: { include: { company: true } } }, orderBy: { createdAt: "desc" }, take: 100 });
  return Response.json({ drafts });
}

const approvalSchema = z.object({ emailId: z.string().min(1), approve: z.boolean(), verifyContact: z.boolean().default(false), sendNow: z.boolean().default(false) });

export async function POST(request: Request) {
  const parsed = approvalSchema.safeParse(await request.json());
  if (!parsed.success) return Response.json({ error: parsed.error.flatten() }, { status: 400 });
  const email = await prisma.emailSent.findUnique({ where: { id: parsed.data.emailId }, include: { contact: true } });
  if (!email) return Response.json({ error: "Draft not found" }, { status: 404 });
  if (!parsed.data.approve) {
    await prisma.emailSent.update({ where: { id: email.id }, data: { status: "UNSUBSCRIBED" } });
    return Response.json({ approved: false });
  }
  if (parsed.data.verifyContact) await prisma.contact.update({ where: { id: email.contactId }, data: { verificationStatus: "VALID" } });
  await prisma.emailSent.update({ where: { id: email.id }, data: { status: parsed.data.sendNow ? "SCHEDULED" : "APPROVED", scheduledAt: parsed.data.sendNow ? new Date() : null } });
  if (parsed.data.sendNow) await enqueueSendEmail({ emailId: email.id });
  return Response.json({ approved: true, queued: parsed.data.sendNow }, { status: 202 });
}
