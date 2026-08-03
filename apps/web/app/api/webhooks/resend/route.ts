import { z } from "zod";
import { Prisma } from "@prisma/client";
import { prisma } from "@nexstudio/db";

export const runtime = "nodejs";

const eventSchema = z.object({ type: z.string(), data: z.object({ email_id: z.string().optional(), id: z.string().optional(), reason: z.string().optional() }).passthrough() }).passthrough();

export async function POST(request: Request) {
  const parsed = eventSchema.safeParse(await request.json());
  if (!parsed.success) return Response.json({ error: "Invalid webhook" }, { status: 400 });
  const providerId = parsed.data.data.email_id ?? parsed.data.data.id;
  if (!providerId) return Response.json({ accepted: true });
  const email = await prisma.emailSent.findFirst({ where: { providerId } });
  if (!email) return Response.json({ accepted: true });
  const status = parsed.data.type.includes("bounced") ? "BOUNCED" : parsed.data.type.includes("delivered") ? "DELIVERED" : email.status;
  await prisma.emailSent.update({ where: { id: email.id }, data: { status } });
  await prisma.emailEvent.create({ data: { emailId: email.id, type: parsed.data.type, providerId, metadata: parsed.data.data as Prisma.InputJsonObject } });
  return Response.json({ accepted: true });
}
