export const metadata = {
  title: "Flow Healer Demo Todos",
  description: "Next.js sandbox app used for Flow Healer regression testing.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: "2rem" }}>
        {children}
      </body>
    </html>
  );
}
