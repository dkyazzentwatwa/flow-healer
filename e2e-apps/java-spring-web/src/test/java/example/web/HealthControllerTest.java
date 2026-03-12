package example.web;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.cookie;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest({HealthController.class, LoginController.class, DashboardController.class})
class HealthControllerTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void healthEndpointReturnsOk() throws Exception {
        mockMvc.perform(get("/healthz"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void loginEndpointIssuesCookieBackedSession() throws Exception {
        mockMvc.perform(post("/login").param("email", "seeded-admin@example.com"))
            .andExpect(status().isFound())
            .andExpect(header().string("Location", "/dashboard"))
            .andExpect(cookie().value("healer_session", "seeded-admin@example.com"));
    }

    @Test
    void dashboardRendersFixtureCookieIdentity() throws Exception {
        mockMvc.perform(get("/dashboard").cookie(new Cookie("healer_session", "seeded-admin")))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("seeded-admin")))
            .andExpect(content().string(containsString("Seeded alerts are ready.")));
    }
}
