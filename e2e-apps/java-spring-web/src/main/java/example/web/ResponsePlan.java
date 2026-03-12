package example.web;

import java.util.LinkedHashMap;
import java.util.Map;

public final class ResponsePlan {
    private final int status;
    private final String contentType;
    private final String body;
    private final Map<String, String> headers;

    public ResponsePlan(int status, String contentType, String body, Map<String, String> headers) {
        this.status = status;
        this.contentType = contentType;
        this.body = body;
        this.headers = Map.copyOf(headers);
    }

    public int status() {
        return status;
    }

    public String contentType() {
        return contentType;
    }

    public String body() {
        return body;
    }

    public Map<String, String> headers() {
        return headers;
    }

    public ResponsePlan withHeader(String name, String value) {
        Map<String, String> updatedHeaders = new LinkedHashMap<>(headers);
        updatedHeaders.put(name, value);
        return new ResponsePlan(status, contentType, body, updatedHeaders);
    }

    public static ResponsePlan html(int status, String body) {
        return new ResponsePlan(status, "text/html; charset=utf-8", body, Map.of());
    }

    public static ResponsePlan json(int status, String body) {
        return new ResponsePlan(status, "application/json; charset=utf-8", body, Map.of());
    }

    public static ResponsePlan text(int status, String body) {
        return new ResponsePlan(status, "text/plain; charset=utf-8", body, Map.of());
    }

    public static ResponsePlan redirect(String location) {
        return text(302, "").withHeader("Location", location);
    }
}
