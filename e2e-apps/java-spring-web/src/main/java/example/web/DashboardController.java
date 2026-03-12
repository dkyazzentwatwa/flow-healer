package example.web;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.util.HtmlUtils;

@Controller
public class DashboardController {
    @GetMapping(value = "/dashboard", produces = MediaType.TEXT_HTML_VALUE)
    @ResponseBody
    public String dashboard(@CookieValue(name = "healer_session", required = false) String userEmail) {
        if (userEmail == null || userEmail.isBlank()) {
            return """
                <h1>Dashboard</h1>
                <p id="session-user">anonymous</p>
                <p>Use the login form to create a session.</p>
                """;
        }
        return """
            <h1>Dashboard</h1>
            <p id="session-user">%s</p>
            <p>Seeded alerts are ready.</p>
            """.formatted(HtmlUtils.htmlEscape(userEmail));
    }
}
