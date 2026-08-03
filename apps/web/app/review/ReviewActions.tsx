"use client";

import { useState } from "react";

export function ReviewActions({ emailId, recipient, subject, body }: { emailId: string; recipient: string; subject: string; body: string }) {
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  async function act(payload: { approve: boolean; verifyContact?: boolean; sendNow?: boolean }) {
    setBusy(true); setStatus("");
    try {
      const response = await fetch("/api/review", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ emailId, ...payload }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error?.message ?? result.error ?? "Action failed");
      setStatus(payload.approve ? (payload.sendNow ? "Queued for sending" : "Approved") : "Rejected");
    } catch (error) { setStatus(error instanceof Error ? error.message : "Action failed"); }
    finally { setBusy(false); }
  }
  async function approveAndCopy() {
    await act({ approve: true, verifyContact: true });
    await navigator.clipboard.writeText(`To: ${recipient}\nSubject: ${subject}\n\n${body}`);
    setStatus("Approved and copied");
  }
  return <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
    <button disabled={busy} onClick={() => act({ approve: true })}>Approve draft</button>
    <button disabled={busy} onClick={approveAndCopy}>Approve &amp; copy email</button>
    <a href={`mailto:${encodeURIComponent(recipient)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`}>Open mail app</a>
    <button disabled={busy} onClick={() => act({ approve: false })}>Reject</button>
    {status && <span style={{ color: status === "Approved and copied" ? "#8ff0bd" : "#aab4d1", fontSize: 13 }}>{status}</span>}
  </div>;
}
