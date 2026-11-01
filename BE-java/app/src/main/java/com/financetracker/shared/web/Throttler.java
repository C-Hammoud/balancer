package com.financetracker.shared.web;

import java.time.Clock;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

import com.financetracker.shared.error.ApiException;

/**
 * DRF SimpleRateThrottle: sliding window per (scope, ident), in memory per process like
 * Django's LocMemCache. Rates look like "10/min" or "5/hour".
 */
@Component
public class Throttler {

    private final Map<String, Deque<Double>> history = new ConcurrentHashMap<>();
    private final Clock clock;

    public Throttler(Clock clock) {
        this.clock = clock;
    }

    /** Raise 429 when the scope's rate is exceeded; records the request otherwise. */
    public void check(String scope, String rate, String ident) {
        if (rate == null || rate.isBlank()) {
            return;
        }
        String[] parts = rate.strip().split("/");
        int numRequests = Integer.parseInt(parts[0]);
        int duration = switch (parts[1].charAt(0)) {
            case 's' -> 1;
            case 'm' -> 60;
            case 'h' -> 3600;
            case 'd' -> 86400;
            default -> throw new IllegalArgumentException("Bad throttle rate " + rate);
        };
        String key = "throttle_" + scope + "_" + ident;
        double now = clock.millis() / 1000.0;
        Deque<Double> h = history.computeIfAbsent(key, k -> new ArrayDeque<>());
        synchronized (h) {
            while (!h.isEmpty() && h.peekLast() <= now - duration) {
                h.pollLast();
            }
            if (h.size() >= numRequests) {
                double remaining = h.isEmpty() ? duration : duration - (now - h.peekLast());
                int available = numRequests - h.size() + 1;
                double wait = available <= 0 ? remaining : remaining / available;
                long seconds = (long) Math.ceil(wait);
                HttpHeaders headers = new HttpHeaders();
                headers.set(HttpHeaders.RETRY_AFTER, String.valueOf(seconds));
                String detail = "Request was throttled. Expected available in " + seconds
                        + (seconds == 1 ? " second." : " seconds.");
                throw new ApiException(HttpStatus.TOO_MANY_REQUESTS, ApiException.detailBody(detail), headers);
            }
            h.addFirst(now);
        }
    }

    /** DRF get_ident with NUM_PROXIES=None: whole X-Forwarded-For (whitespace removed) or remote address. */
    public static String ident(HttpServletRequest request) {
        String xff = request.getHeader("X-Forwarded-For");
        if (xff != null && !xff.isEmpty()) {
            return xff.replaceAll("\\s+", "");
        }
        return request.getRemoteAddr();
    }

    /** Clears all counters (tests). */
    public void reset() {
        history.clear();
    }
}
