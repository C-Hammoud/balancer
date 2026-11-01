package com.financetracker.shared.web;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import jakarta.servlet.http.HttpServletResponse;

import tools.jackson.databind.json.JsonMapper;

/** Writes a JSON body directly to the servlet response (used by filters, before MVC runs). */
public final class JsonResponses {

    private static final JsonMapper JSON = JsonMapper.builder().build();

    private JsonResponses() {
    }

    public static void write(HttpServletResponse response, int status, Object body, Map<String, String> headers)
            throws IOException {
        response.setStatus(status);
        headers.forEach(response::setHeader);
        response.setContentType("application/json");
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.getOutputStream().write(JSON.writeValueAsBytes(body));
    }
}
