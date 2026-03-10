import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NobiBot Dashboard",
  description: "Professional Cryptocurrency Trading Bot Dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-zinc-950 antialiased">{children}</body>
    </html>
  );
}
