import { Queue } from "bullmq";
import { getEnv } from "@nexstudio/core";
import { queueNames, type ApolloDiscoveryJob, type ApolloCsvImportJob, type EmailGenerationJob, type ScoreLeadJob, type SendEmailJob, type WebsiteAuditJob, type FollowupJob } from "./contracts.js";

const connection = { url: getEnv().REDIS_URL };

export const discoveryQueue = new Queue(queueNames.discovery, { connection });
export const researchQueue = new Queue(queueNames.research, { connection });
export const outreachQueue = new Queue(queueNames.outreach, { connection });
export const followupQueue = new Queue(queueNames.followups, { connection });

async function enqueue(queue: Queue, name: string, data: object): Promise<string> {
  const job = await queue.add(name, data, { attempts: 5, backoff: { type: "exponential", delay: 5000 }, removeOnComplete: 1000, removeOnFail: 5000 });
  return job.id ?? "";
}

export async function enqueueApolloDiscovery(data: ApolloDiscoveryJob): Promise<string> {
  return enqueue(discoveryQueue, "discover-apollo-companies", data);
}

export const enqueueApolloCsvImport = (data: ApolloCsvImportJob) => enqueue(discoveryQueue, "import-apollo-csv", data);

export const enqueueWebsiteAudit = (data: WebsiteAuditJob) => enqueue(researchQueue, "audit-website", data);
export const enqueueLeadScore = (data: ScoreLeadJob) => enqueue(researchQueue, "score-lead", data);
export const enqueueEmailGeneration = (data: EmailGenerationJob) => enqueue(outreachQueue, "generate-email", data);
export const enqueueSendEmail = (data: SendEmailJob) => enqueue(outreachQueue, "send-email", data);
export const enqueueFollowup = (data: FollowupJob, delay = 0) => followupQueue.add("follow-up", data, { delay, attempts: 5, backoff: { type: "exponential", delay: 5000 }, removeOnComplete: 1000, removeOnFail: 5000 }).then((job) => job.id ?? "");
