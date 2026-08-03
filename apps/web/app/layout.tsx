import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "NexStudio Lead Engine",
  description: "Apollo-first lead qualification and outreach workspace"
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, background: "#0b1020", color: "#eef2ff", fontFamily: "system-ui, sans-serif" }}>
        {children}
      </body>
    </html>
  );
}
