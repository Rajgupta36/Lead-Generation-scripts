import { Worker } from "bullmq";
import { ApolloPipelineService } from "@nexstudio/agents";
import { getEnv } from "@nexstudio/core";
import { logger } from "@nexstudio/observability";
import { queueNames } from "@nexstudio/queues";

const connection = { url: getEnv().REDIS_URL };
const pipeline = () => new ApolloPipelineService();

const discoveryWorker = new Worker(queueNames.discovery, async (job) => {
  if (job.name === "discover-apollo-companies") return { count: await pipeline().discover(job.data.organizationId, job.data.runId, job.data.filters) };
  if (job.name === "import-apollo-csv") return { count: await pipeline().importCsv(job.data.organizationId, job.data.runId, job.data.csv) };
  throw new Error(`Unknown discovery job: ${job.name}`);
}, { connection, concurrency: 3 });

const researchWorker = new Worker(queueNames.research, async (job) => {
  if (job.name === "audit-website") return pipeline().audit(job.data.companyId, job.data.url);
  if (job.name === "score-lead") return pipeline().score(job.data.companyId);
  throw new Error(`Unknown research job: ${job.name}`);
}, { connection, concurrency: 5 });

const outreachWorker = new Worker(queueNames.outreach, async (job) => {
  if (job.name === "generate-email") return pipeline().generateEmail(job.data.contactId, job.data.sequenceId);
  if (job.name === "send-email") return pipeline().sendEmail(job.data.emailId);
  throw new Error(`Unknown outreach job: ${job.name}`);
}, { connection, concurrency: 2 });

const followupWorker = new Worker(queueNames.followups, async (job) => {
  if (job.name !== "follow-up") throw new Error(`Unknown follow-up job: ${job.name}`);
  return pipeline().followup(job.data.emailId, job.data.step);
}, { connection, concurrency: 2 });

for (const worker of [discoveryWorker, researchWorker, outreachWorker, followupWorker]) {
  worker.on("failed", (job, error) => logger.error("Worker job failed", { queue: worker.name, jobId: job?.id, error: error.message }));
}

logger.info("NexStudio worker started", { queues: Object.values(queueNames) });
