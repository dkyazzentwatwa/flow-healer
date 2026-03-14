package example.web;

public class LoginController {
    private static final String ANONYMOUS_SESSION_USER = "anonymous";
    private static final String DEFAULT_SESSION_EMAIL = "admin@example.com";

    public ResponsePlan loginForm(String sessionUser) {
        String fixtureProfile = resolveSessionUser(sessionUser, ANONYMOUS_SESSION_USER);
        return ResponsePlan.html(
            200,
            """
            <h1>Java Spring Web</h1>
            <p class="fixture-profile">%s</p>
            <p>Evidence TC 3</p>
            <form action="/login" method="post">
              <label>Email <input name="email" type="email" /></label>
              <label>Password <input name="password" type="password" /></label>
              <button type="submit">Sign in</button>
            </form>
            """.formatted(escapeHtml(fixtureProfile))
        );
    }

    public ResponsePlan createSession(String email) {
        String resolvedEmail = resolveSessionUser(email, DEFAULT_SESSION_EMAIL);
        return ResponsePlan.redirect("/dashboard")
            .withHeader("Set-Cookie", "healer_session=" + resolvedEmail + "; Path=/; SameSite=Lax");
    }

    public ResponsePlan destroySession() {
        return ResponsePlan.redirect("/login")
            .withHeader("Set-Cookie", "healer_session=; Path=/; Max-Age=0");
    }

    private static String resolveSessionUser(String rawSessionUser, String defaultValue) {
        if (rawSessionUser == null || rawSessionUser.isBlank()) {
            return defaultValue;
        }
        String trimmedSessionUser = rawSessionUser.trim();
        if (!trimmedSessionUser.matches("[A-Za-z0-9._%+-@]+")) {
            return defaultValue;
        }
        return trimmedSessionUser;
    }

    private static String escapeHtml(String raw) {
        return String.valueOf(raw)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\"", "&quot;");
    }
}
