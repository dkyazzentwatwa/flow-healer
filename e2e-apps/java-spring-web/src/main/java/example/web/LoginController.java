package example.web;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.util.HtmlUtils;

@Controller
public class LoginController {
    @GetMapping(value = {"/", "/login"}, produces = MediaType.TEXT_HTML_VALUE)
    @ResponseBody
    public String loginForm(@CookieValue(name = "healer_session", required = false) String sessionUser) {
        String fixtureProfile = (sessionUser == null || sessionUser.isBlank()) ? "anonymous" : sessionUser;
        return """
            <h1>Java Spring Web</h1>
            <p class="fixture-profile">%s</p>
            <form action="/login" method="post">
              <label>Email <input name="email" type="email" /></label>
              <label>Password <input name="password" type="password" /></label>
              <button type="submit">Sign in</button>
            </form>
            """.formatted(HtmlUtils.htmlEscape(fixtureProfile));
    }

    @PostMapping("/login")
    public ResponseEntity<Void> createSession(
        @RequestParam(defaultValue = "admin@example.com") String email
    ) {
        ResponseCookie cookie = ResponseCookie.from("healer_session", email)
            .path("/")
            .sameSite("Lax")
            .build();
        return ResponseEntity.status(HttpStatus.FOUND)
            .header(HttpHeaders.LOCATION, "/dashboard")
            .header(HttpHeaders.SET_COOKIE, cookie.toString())
            .build();
    }

    @PostMapping("/logout")
    public ResponseEntity<Void> destroySession() {
        ResponseCookie cookie = ResponseCookie.from("healer_session", "")
            .path("/")
            .maxAge(0)
            .build();
        return ResponseEntity.status(HttpStatus.FOUND)
            .header(HttpHeaders.LOCATION, "/login")
            .header(HttpHeaders.SET_COOKIE, cookie.toString())
            .build();
    }
}
