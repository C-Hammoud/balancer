package com.financetracker.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.gateway.route.Route;
import org.springframework.cloud.gateway.route.RouteLocator;

@SpringBootTest(properties = {
        "BACKEND_URL=http://backend:8000",
        "FINANCE_URL=http://finance:8000",
})
class GatewayRoutingTest {

    @Autowired
    RouteLocator routes;

    @Test
    void eachAreaHasItsOwnUpstream() {
        List<Route> all = routes.getRoutes().collectList().block();
        Map<String, String> uris = all.stream()
                .collect(Collectors.toMap(Route::getId, r -> r.getUri().toString()));
        assertThat(uris).containsEntry("access", "http://backend:8000")
                .containsEntry("notifications", "http://backend:8000")
                .containsEntry("finance", "http://finance:8000")
                .containsEntry("default", "http://backend:8000");
        assertThat(all.get(all.size() - 1).getId()).isEqualTo("default");
    }
}
