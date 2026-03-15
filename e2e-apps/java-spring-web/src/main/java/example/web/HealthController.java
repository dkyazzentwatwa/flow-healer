package example.web;

public class HealthController {
    private static final String FIXTURE_PROFILE = "anonymous";
    private static final String SERVICE_NAME = "Flow Healer Java Spring Web";
    private static final String SERVICE_LANGUAGE = "java";
    private static final String SERVICE_FRAMEWORK = "spring";
    private static final String HEALTH_PAYLOAD_TEMPLATE = """
        {
          "status":"ok",
          "fixture_profile":"%s",
          "service":{
            "name":"%s",
            "language":"%s",
            "framework":"%s"
          }
        }
        """.stripIndent();

    public ResponsePlan health() {
        return ResponsePlan.json(
            200,
            HEALTH_PAYLOAD_TEMPLATE.formatted(
                FIXTURE_PROFILE,
                SERVICE_NAME,
                SERVICE_LANGUAGE,
                SERVICE_FRAMEWORK
            )
        );
    }
}
