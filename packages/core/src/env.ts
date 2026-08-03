import { z } from "zod";

const envSchema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  DATABASE_URL: z.string().url().default("postgresql://nexstudio:nexstudio@postgres:5432/nexstudio"),
  REDIS_URL: z.string().url().default("redis://redis:6379"),
  APOLLO_API_KEY: z.string().min(1).optional(),
  APOLLO_BASE_URL: z.string().url().default("https://api.apollo.io"),
  OPENAI_API_KEY: z.string().min(1).optional(),
  RESEND_API_KEY: z.string().min(1).optional(),
  OUTREACH_FROM_EMAIL: z.string().email().optional(),
  NEXTAUTH_SECRET: z.string().min(32).optional(),
  NEXTAUTH_URL: z.string().url().default("http://localhost:3000")
});

export type AppEnv = z.infer<typeof envSchema>;

export function getEnv(input: NodeJS.ProcessEnv = process.env): AppEnv {
  return envSchema.parse(input);
}
