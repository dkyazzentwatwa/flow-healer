package example.web;

public class HealthControllerTest {
    public static void main(String[] args) {
        healthEndpointReturnsOk();
        loginFormRendersDeterministicEvidenceMarker();
        loginFormEscapesSessionUser();
        loginEndpointIssuesCookieBackedSession();
        loginEndpointFallsBackForBlankEmailInput();
        loginEndpointFallsBackForMalformedEmailInput();
        dashboardRendersFixtureCookieIdentity();
    }

    private static void healthEndpointReturnsOk() {
        ResponsePlan response = new HealthController().health();
        assertEquals(200, response.status(), "health status");
        assertContains(response.body(), "\"status\":\"ok\"", "health body");
    }

    private static void loginFormRendersDeterministicEvidenceMarker() {
        ResponsePlan response = new LoginController().loginForm("");
        assertEquals(200, response.status(), "login form status");
        assertContains(response.body(), "Evidence TC 3", "login form evidence marker");
    }

    private static void loginFormEscapesSessionUser() {
        String sessionUserWithApostrophe = "seeded-admin'o@example.com";
        ResponsePlan response = new LoginController().loginForm(sessionUserWithApostrophe);
        assertEquals(200, response.status(), "login form status");
        assertContains(
            response.body(),
            "seeded-admin&#x27;o@example.com",
            "login form escapes apostrophes in session user"
        );
        assertNotContains(response.body(), sessionUserWithApostrophe, "login form raw session user");
    }

    private static void loginEndpointIssuesCookieBackedSession() {
        ResponsePlan response = new LoginController().createSession("seeded-admin@example.com");
        assertEquals(302, response.status(), "login status");
        assertEquals("/dashboard", response.headers().get("Location"), "login redirect");
        assertContains(
            response.headers().get("Set-Cookie"),
            "healer_session=seeded-admin@example.com",
            "login cookie"
        );
    }

    private static void loginEndpointFallsBackForBlankEmailInput() {
        ResponsePlan response = new LoginController().createSession("   ");
        assertContains(
            response.headers().get("Set-Cookie"),
            "healer_session=admin@example.com",
            "blank email cookie fallback"
        );
    }

    private static void loginEndpointFallsBackForMalformedEmailInput() {
        ResponsePlan response = new LoginController().createSession("seeded-admin@example.com\nSet-Cookie:admin\n");
        assertContains(
            response.headers().get("Set-Cookie"),
            "healer_session=admin@example.com",
            "malformed email cookie fallback"
        );
    }

    private static void dashboardRendersFixtureCookieIdentity() {
        ResponsePlan anonymous = new DashboardController().dashboard("");
        assertEquals(302, anonymous.status(), "anonymous redirect status");
        assertEquals("/login", anonymous.headers().get("Location"), "anonymous redirect location");

        ResponsePlan authenticated = new DashboardController().dashboard("seeded-admin");
        assertEquals(200, authenticated.status(), "dashboard status");
        assertContains(authenticated.body(), "seeded-admin", "dashboard identity");
        assertContains(authenticated.body(), "Seeded alerts are ready.", "dashboard fixture text");
    }

    private static void assertEquals(Object expected, Object actual, String label) {
        if ((expected == null && actual != null) || (expected != null && !expected.equals(actual))) {
            throw new AssertionError(label + " expected " + expected + " but was " + actual);
        }
    }

    private static void assertContains(String body, String expected, String label) {
        if (body == null || !body.contains(expected)) {
            throw new AssertionError(label + " missing expected fragment: " + expected);
        }
    }

    private static void assertNotContains(String body, String unexpected, String label) {
        if (body != null && body.contains(unexpected)) {
            throw new AssertionError(label + " contains unexpected fragment: " + unexpected);
        }
    }
}
