import { prisma } from "@nexstudio/db";
import { enqueueApolloCsvImport } from "@nexstudio/queues";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const form = await request.formData();
  const organizationId = String(form.get("organizationId") ?? "");
  const name = String(form.get("name") ?? "Apollo CSV import");
  const file = form.get("file");
  if (!organizationId || !(file instanceof File)) return Response.json({ error: "organizationId and CSV file are required" }, { status: 400 });
  const csv = await file.text();
  if (!csv.trim() || csv.length > 10_000_000) return Response.json({ error: "CSV is empty or exceeds the 10MB limit" }, { status: 400 });
  const run = await prisma.apolloSearchRun.create({ data: { organizationId, name, filters: { source: "apollo_csv" } } });
  const jobId = await enqueueApolloCsvImport({ organizationId, runId: run.id, csv });
  return Response.json({ accepted: true, runId: run.id, jobId }, { status: 202 });
}
