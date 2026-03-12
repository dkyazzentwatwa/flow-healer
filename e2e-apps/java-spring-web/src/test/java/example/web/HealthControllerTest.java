package example.web;

public class HealthControllerTest {
    public static void main(String[] args) {
        healthEndpointReturnsOk();
        loginEndpointIssuesCookieBackedSession();
        dashboardRendersFixtureCookieIdentity();
    }

    private static void healthEndpointReturnsOk() {
        ResponsePlan response = new HealthController().health();
        assertEquals(200, response.status(), "health status");
        assertContains(response.body(), "\"status\":\"ok\"", "health body");
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
}
