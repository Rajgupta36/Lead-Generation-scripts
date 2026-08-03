export type EmailSender = { send(input: { to: string; subject: string; html: string; from: string }): Promise<{ providerId: string }> };

export class ResendEmailSender implements EmailSender {
  constructor(private readonly apiKey: string, private readonly fetcher: typeof fetch = fetch) {}

  async send(input: { to: string; subject: string; html: string; from: string }): Promise<{ providerId: string }> {
    const response = await this.fetcher("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${this.apiKey}`, "Content-Type": "application/json" },
      body: JSON.stringify(input)
    });
    if (!response.ok) throw new Error(`Resend request failed with ${response.status}`);
    const result = await response.json() as { id?: string };
    if (!result.id) throw new Error("Resend returned no message id");
    return { providerId: result.id };
  }
}
