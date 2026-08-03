"use client";

import { useState } from "react";

export function ReviewActions({ emailId }: { emailId: string }) {
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
  return <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
    <button disabled={busy} onClick={() => act({ approve: true })}>Approve draft</button>
    <button disabled={busy} onClick={() => act({ approve: true, verifyContact: true, sendNow: true })}>Verify &amp; queue send</button>
    <button disabled={busy} onClick={() => act({ approve: false })}>Reject</button>
    {status && <span style={{ color: status === "Queued for sending" ? "#8ff0bd" : "#aab4d1", fontSize: 13 }}>{status}</span>}
  </div>;
}
