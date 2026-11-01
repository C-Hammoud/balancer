package com.financetracker.shared.error;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;

/**
 * An error response with the exact JSON body Django REST Framework would produce,
 * e.g. {"detail": "..."} or {"field": ["message"]}.
 */
public class ApiException extends RuntimeException {

    private final HttpStatus status;
    private final Object body;
    private final HttpHeaders headers;

    public ApiException(HttpStatus status, Object body) {
        this(status, body, new HttpHeaders());
    }

    public ApiException(HttpStatus status, Object body, HttpHeaders headers) {
        super(String.valueOf(body));
        this.status = status;
        this.body = body;
        this.headers = headers;
    }

    public HttpStatus status() {
        return status;
    }

    public Object body() {
        return body;
    }

    public HttpHeaders headers() {
        return headers;
    }

    /** {"detail": message} */
    public static ApiException detail(HttpStatus status, String message) {
        return new ApiException(status, detailBody(message));
    }

    public static ApiException badRequest(String message) {
        return detail(HttpStatus.BAD_REQUEST, message);
    }

    /** {"field": ["message"]} with status 400. */
    public static ApiException field(String field, String message) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put(field, List.of(message));
        return new ApiException(HttpStatus.BAD_REQUEST, body);
    }

    public static ApiException notFound() {
        return detail(HttpStatus.NOT_FOUND, "Not found.");
    }

    public static ApiException notFound(String message) {
        return detail(HttpStatus.NOT_FOUND, message);
    }

    public static ApiException forbidden() {
        return detail(HttpStatus.FORBIDDEN, "You do not have permission to perform this action.");
    }

    public static ApiException forbidden(String message) {
        return detail(HttpStatus.FORBIDDEN, message);
    }

    /** DRF NotAuthenticated / AuthenticationFailed: 401 with a Bearer challenge. */
    public static ApiException unauthorized(Map<String, Object> body) {
        HttpHeaders headers = new HttpHeaders();
        headers.set(HttpHeaders.WWW_AUTHENTICATE, "Bearer realm=\"api\"");
        return new ApiException(HttpStatus.UNAUTHORIZED, body, headers);
    }

    public static ApiException unauthorized(String message) {
        return unauthorized(detailBody(message));
    }

    public static Map<String, Object> detailBody(String message) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("detail", message);
        return body;
    }
}
