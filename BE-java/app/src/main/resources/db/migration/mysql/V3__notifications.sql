-- Notification management: in-app inbox (Django app_notifications).

CREATE TABLE ntf_notifications (
    id          VARCHAR(64)              PRIMARY KEY,
    user_id     VARCHAR(64)              NOT NULL,
    kind        VARCHAR(40)              NOT NULL,
    title       VARCHAR(200)             NOT NULL,
    body        TEXT NOT NULL,
    link        VARCHAR(300)             NOT NULL DEFAULT '',
    related_id  VARCHAR(64)              NOT NULL DEFAULT '',
    fingerprint VARCHAR(255)             NOT NULL DEFAULT '',
    is_read     BOOLEAN                  NOT NULL DEFAULT FALSE,
    created_at  DATETIME(6)             
);
CREATE INDEX ix_ntf_notifications_user ON ntf_notifications (user_id);
CREATE INDEX ix_ntf_notifications_fingerprint ON ntf_notifications (user_id, fingerprint);
