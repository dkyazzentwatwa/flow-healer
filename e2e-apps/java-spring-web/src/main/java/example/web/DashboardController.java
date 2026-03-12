package example.web;

public class DashboardController {
    public ResponsePlan dashboard(String userEmail) {
        if (userEmail == null || userEmail.isBlank()) {
            return ResponsePlan.redirect("/login");
        }
        return ResponsePlan.html(
            200,
            """
            <h1>Dashboard</h1>
            <p id="session-user">%s</p>
            <p>Seeded alerts are ready.</p>
            """.formatted(escapeHtml(userEmail))
        );
    }

    private static String escapeHtml(String raw) {
        return String.valueOf(raw)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\"", "&quot;");
    }
}
