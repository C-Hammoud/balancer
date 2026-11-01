package com.financetracker.notifications.inbox;

import java.util.List;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.financetracker.shared.error.ApiException;
import com.financetracker.shared.security.CurrentUser;

/** /api/v1/notifications/* */
@RestController
@RequestMapping("/api/v1/notifications")
class InboxController {

    private final InboxService inbox;

    InboxController(InboxService inbox) {
        this.inbox = inbox;
    }

    @GetMapping("/")
    List<Map<String, Object>> list(@RequestParam(required = false) String unread) {
        return inbox.list(CurrentUser.require().userId(), "1".equals(unread) || "true".equals(unread));
    }

    @GetMapping("/count/")
    Map<String, Object> count() {
        return Map.of("unread", inbox.unreadCount(CurrentUser.require().userId()));
    }

    @PostMapping("/{id}/read/")
    Map<String, Object> read(@PathVariable String id) {
        return inbox.markRead(CurrentUser.require().userId(), id).orElseThrow(ApiException::notFound);
    }

    @PostMapping("/read-all/")
    Map<String, Object> readAll() {
        return Map.of("marked", inbox.markAllRead(CurrentUser.require().userId()));
    }
}
