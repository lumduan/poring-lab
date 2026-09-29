import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "poring-lab console",
  description: "Live view of, and input into, the poring-lab RDP session",
};

// System fonts only: a LAN lab console has no business fetching fonts from Google at build time.
export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full bg-neutral-950 text-neutral-100">{children}</body>
    </html>
  );
}
