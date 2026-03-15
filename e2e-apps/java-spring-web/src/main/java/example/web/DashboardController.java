package example.web;

public class DashboardController {
    public ResponsePlan dashboard(String userEmail) {
        if (userEmail == null || userEmail.isBlank()) {
            return ResponsePlan.redirect("/login");
        }
        String escapedUser = escapeHtml(userEmail);
        return ResponsePlan.html(
            200,
            """
            <section style="min-height: 100vh; padding: 48px; background: #f4e7d3; color: #3f2f21; font-family: Georgia, 'Times New Roman', serif;">
                <div style="max-width: 760px; margin: 0 auto; background: rgba(255, 249, 240, 0.92); border: 1px solid #dcc7aa; border-radius: 18px; padding: 32px; box-shadow: 0 18px 40px rgba(95, 70, 40, 0.12);">
                    <div style="font-size: 14px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #8a5a2b;">Java Browser Signal J1</div>
                    <h1 style="margin: 16px 0 12px; font-size: 40px;">Dashboard</h1>
                    <div id="session-user" style="margin-bottom: 20px; font-size: 16px;">Signed in as %s</div>
                    <div style="margin-bottom: 20px; font-size: 15px; font-weight: 600; color: #6d4c2c;">Seeded alerts are ready.</div>
                    <p style="margin: 0 0 16px; font-size: 18px; line-height: 1.7;">Autonomous code agents read issue instructions, edit only the allowed files, run checks, and report their progress back on GitHub. They keep the work scoped so each change lines up with the task contract and leaves a clear audit trail.</p>
                    <p style="margin: 0 0 16px; font-size: 18px; line-height: 1.7;">Autonomous code agents read the issue instructions, make the smallest safe edit, and run the requested validation command before reporting the outcome. The dashboard surface documents that workflow so the next reviewer easily understands what changed and why.</p>
                    <p style="margin: 0 0 16px; font-size: 18px; line-height: 1.7;">A healthy run keeps the edit scope tight, executes the requested checks, and publishes artifacts so the repair remains auditable and reproducible.</p>
                    <p style="margin: 0; font-size: 18px; line-height: 1.7;">That workflow helps teams clear routine engineering work faster because small fixes move forward with less manual coordination, while the guardrails keep each automated pass focused, reviewable, and easy to trust.</p>
                </div>
            </section>
            """.formatted(escapedUser)
        );
    }

    private static String escapeHtml(String raw) {
        return String.valueOf(raw)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\"", "&quot;")
            .replace("'", "&#x27;");
    }
}
