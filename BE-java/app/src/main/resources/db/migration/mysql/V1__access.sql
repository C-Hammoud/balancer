-- Access manager: users, profiles, locale preferences, refresh tokens (MySQL 8+).

CREATE TABLE access_users (
    id           BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
    username     VARCHAR(150) NOT NULL,
    email        VARCHAR(254) NOT NULL DEFAULT '',
    first_name   VARCHAR(150) NOT NULL DEFAULT '',
    last_name    VARCHAR(150) NOT NULL DEFAULT '',
    password     VARCHAR(128) NOT NULL DEFAULT '',
    staff        BOOLEAN      NOT NULL DEFAULT FALSE,
    superuser    BOOLEAN      NOT NULL DEFAULT FALSE,
    active       BOOLEAN      NOT NULL DEFAULT TRUE,
    last_login   DATETIME(6),
    date_joined  DATETIME(6)  NOT NULL,
    CONSTRAINT uq_access_users_username UNIQUE (username)
);
CREATE INDEX ix_access_users_email ON access_users (email);

CREATE TABLE access_user_profiles (
    user_id                   BIGINT      PRIMARY KEY,
    email_verified            BOOLEAN     NOT NULL DEFAULT FALSE,
    email_verified_at         DATETIME(6),
    phone                     VARCHAR(32) NOT NULL DEFAULT '',
    setup_status              VARCHAR(20) NOT NULL DEFAULT 'pending',
    setup_skipped_at          DATETIME(6),
    setup_completed_at        DATETIME(6),
    setup_nudge_push_due_at   DATETIME(6),
    setup_nudge_email_due_at  DATETIME(6),
    setup_nudge_push_sent_at  DATETIME(6),
    setup_nudge_email_sent_at DATETIME(6),
    notify_weekly_summaries   BOOLEAN     NOT NULL DEFAULT TRUE,
    notify_low_balance        BOOLEAN     NOT NULL DEFAULT TRUE,
    notify_setup_nudges       BOOLEAN     NOT NULL DEFAULT TRUE,
    notify_plan_updates       BOOLEAN     NOT NULL DEFAULT TRUE,
    savings_target_pct        INTEGER     NOT NULL DEFAULT 20
);
CREATE INDEX ix_access_user_profiles_setup ON access_user_profiles (setup_status);

CREATE TABLE access_user_preferences (
    user_id          VARCHAR(64) PRIMARY KEY,
    timezone         VARCHAR(64) NOT NULL DEFAULT '',
    country          VARCHAR(8)  NOT NULL DEFAULT '',
    default_currency VARCHAR(3)  NOT NULL DEFAULT 'USD',
    updated_at       DATETIME(6)
);

CREATE TABLE access_refresh_tokens (
    jti            VARCHAR(255) PRIMARY KEY,
    user_id        BIGINT,
    token          VARCHAR(2048),
    created_at     DATETIME(6),
    expires_at     DATETIME(6)  NOT NULL,
    blacklisted_at DATETIME(6)
);
CREATE INDEX ix_access_refresh_tokens_user ON access_refresh_tokens (user_id);
