package example;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import example.web.DashboardController;
import example.web.HealthController;
import example.web.LoginController;
import example.web.ResponsePlan;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.Executors;

public class Application {
    public static void main(String[] args) throws Exception {
        String host = System.getenv().getOrDefault("HOST", "127.0.0.1");
        int port = Integer.parseInt(System.getenv().getOrDefault("PORT", "3201"));
        HttpServer server = HttpServer.create(new InetSocketAddress(host, port), 0);
        server.setExecutor(Executors.newCachedThreadPool());

        HealthController healthController = new HealthController();
        LoginController loginController = new LoginController();
        DashboardController dashboardController = new DashboardController();

        server.createContext("/", exchange -> dispatch(exchange, healthController, loginController, dashboardController));
        server.start();
        System.out.printf("java-spring-web listening on http://%s:%d%n", host, port);
    }

    private static void dispatch(
        HttpExchange exchange,
        HealthController healthController,
        LoginController loginController,
        DashboardController dashboardController
    ) throws IOException {
        String path = exchange.getRequestURI().getPath();
        String method = exchange.getRequestMethod();
        String sessionUser = readCookie(exchange, "healer_session");
        ResponsePlan plan;

        if ("GET".equals(method) && "/healthz".equals(path)) {
            plan = healthController.health();
        } else if ("GET".equals(method) && ("/".equals(path) || "/login".equals(path))) {
            plan = loginController.loginForm(sessionUser);
        } else if ("POST".equals(method) && "/login".equals(path)) {
            String email = parseFormBody(exchange).getOrDefault("email", "admin@example.com");
            plan = loginController.createSession(email);
        } else if ("POST".equals(method) && "/logout".equals(path)) {
            plan = loginController.destroySession();
        } else if ("GET".equals(method) && "/dashboard".equals(path)) {
            plan = dashboardController.dashboard(sessionUser);
        } else {
            plan = ResponsePlan.text(404, "Not Found");
        }

        writeResponse(exchange, plan);
    }

    private static Map<String, String> parseFormBody(HttpExchange exchange) throws IOException {
        String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
        Map<String, String> values = new LinkedHashMap<>();
        for (String pair : body.split("&")) {
            if (pair.isBlank()) {
                continue;
            }
            String[] parts = pair.split("=", 2);
            String key = URLDecoder.decode(parts[0], StandardCharsets.UTF_8);
            String value = parts.length > 1 ? URLDecoder.decode(parts[1], StandardCharsets.UTF_8) : "";
            values.put(key, value);
        }
        return values;
    }

    private static String readCookie(HttpExchange exchange, String name) {
        String cookieHeader = exchange.getRequestHeaders().getFirst("Cookie");
        if (cookieHeader == null || cookieHeader.isBlank()) {
            return "";
        }
        for (String rawCookie : cookieHeader.split(";")) {
            String trimmed = rawCookie.trim();
            String[] parts = trimmed.split("=", 2);
            if (parts.length == 2 && name.equals(parts[0])) {
                return parts[1];
            }
        }
        return "";
    }

    private static void writeResponse(HttpExchange exchange, ResponsePlan plan) throws IOException {
        exchange.getResponseHeaders().set("Content-Type", plan.contentType());
        for (Map.Entry<String, String> entry : plan.headers().entrySet()) {
            exchange.getResponseHeaders().set(entry.getKey(), entry.getValue());
        }
        byte[] body = plan.body().getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(plan.status(), body.length);
        exchange.getResponseBody().write(body);
        exchange.close();
    }
}
