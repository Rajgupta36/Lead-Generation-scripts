import { z } from "zod";
import { prisma } from "@nexstudio/db";
import { enqueueApolloDiscovery } from "@nexstudio/queues";

export const runtime = "nodejs";

const requestSchema = z.object({
  organizationId: z.string().min(1),
  runId: z.string().min(1).optional(),
  name: z.string().min(1).default("Apollo search"),
  filters: z.object({
    titles: z.array(z.string()).optional(),
    locations: z.array(z.string()).optional(),
    industries: z.array(z.string()).optional(),
    employeeRanges: z.array(z.string()).optional(),
    keywords: z.array(z.string()).optional(),
    page: z.number().int().positive().optional(),
    perPage: z.number().int().min(1).max(100).optional()
  })
});

export async function POST(request: Request) {
  const parsed = requestSchema.safeParse(await request.json());
  if (!parsed.success) return Response.json({ error: parsed.error.flatten() }, { status: 400 });
  const run = await prisma.apolloSearchRun.create({ data: { ...(parsed.data.runId ? { id: parsed.data.runId } : {}), organizationId: parsed.data.organizationId, name: parsed.data.name, filters: parsed.data.filters } });
  const jobId = await enqueueApolloDiscovery({
    organizationId: parsed.data.organizationId,
    runId: run.id,
    filters: {
      titles: parsed.data.filters.titles ?? [],
      locations: parsed.data.filters.locations ?? [],
      industries: parsed.data.filters.industries ?? [],
      employeeRanges: parsed.data.filters.employeeRanges ?? [],
      keywords: parsed.data.filters.keywords ?? [],
      ...(parsed.data.filters.page ? { page: parsed.data.filters.page } : {}),
      ...(parsed.data.filters.perPage ? { perPage: parsed.data.filters.perPage } : {})
    }
  });
  return Response.json({ accepted: true, runId: run.id, jobId }, { status: 202 });
}
