package example.web;

public class HealthController {
    public ResponsePlan health() {
        return ResponsePlan.json(200, "{\"status\":\"ok\"}");
    }
}
