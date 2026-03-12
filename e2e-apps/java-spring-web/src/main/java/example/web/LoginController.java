package example.web;

public class LoginController {
    public ResponsePlan loginForm(String sessionUser) {
        String fixtureProfile = (sessionUser == null || sessionUser.isBlank()) ? "anonymous" : sessionUser;
        return ResponsePlan.html(
            200,
            """
            <h1>Java Spring Web</h1>
            <p class="fixture-profile">%s</p>
            <form action="/login" method="post">
              <label>Email <input name="email" type="email" /></label>
              <label>Password <input name="password" type="password" /></label>
              <button type="submit">Sign in</button>
            </form>
            """.formatted(escapeHtml(fixtureProfile))
        );
    }

    public ResponsePlan createSession(String email) {
        String resolvedEmail = (email == null || email.isBlank()) ? "admin@example.com" : email;
        return ResponsePlan.redirect("/dashboard")
            .withHeader("Set-Cookie", "healer_session=" + resolvedEmail + "; Path=/; SameSite=Lax");
    }

    public ResponsePlan destroySession() {
        return ResponsePlan.redirect("/login")
            .withHeader("Set-Cookie", "healer_session=; Path=/; Max-Age=0");
    }

    private static String escapeHtml(String raw) {
        return String.valueOf(raw)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\"", "&quot;");
    }
}
