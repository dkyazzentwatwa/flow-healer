export const metadata = {
  title: "Flow Healer Todo Sandbox",
  description: "Next.js todo sandbox used for Flow Healer regression testing.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: "2rem" }}>
        <div style={{ display: "grid", gap: "1.5rem" }}>
          <header>
            <h1>Flow Healer Todo Sandbox</h1>
            <p>This Next.js fixture is intentionally small but production-shaped.</p>
          </header>
          <main>{children}</main>
        </div>
      </body>
    </html>
  );
}
