-- Finance module tables (PostgreSQL syntax; also used by H2 in PostgreSQL mode).
-- Ids are strings (Firestore-style auto ids, or migrated ids). User references are plain
-- string ids: no foreign keys across modules.

CREATE TABLE fin_groups (
    id         VARCHAR(64)  PRIMARY KEY,
    name       VARCHAR(120) NOT NULL,
    sort_order INTEGER      NOT NULL DEFAULT 0,
    user_id    VARCHAR(64)  NOT NULL DEFAULT ''
);

CREATE TABLE fin_categories (
    id                 VARCHAR(64)  PRIMARY KEY,
    name               VARCHAR(120) NOT NULL,
    group_id           VARCHAR(64)  NOT NULL,
    include_in_reports BOOLEAN      NOT NULL DEFAULT TRUE,
    sort_order         INTEGER      NOT NULL DEFAULT 0,
    user_id            VARCHAR(64)  NOT NULL DEFAULT ''
);
CREATE INDEX ix_fin_categories_group ON fin_categories (group_id);

CREATE TABLE fin_transactions (
    id                     VARCHAR(64)              PRIMARY KEY,
    user_id                VARCHAR(64)              NOT NULL,
    txn_date               DATE,
    txn_month              VARCHAR(7)               NOT NULL DEFAULT '',
    description            VARCHAR(500)             NOT NULL DEFAULT '',
    category_id            VARCHAR(64),
    classification         VARCHAR(20),
    amount                 NUMERIC(14, 2)           NOT NULL DEFAULT 0,
    direction              VARCHAR(20)              NOT NULL DEFAULT 'expense',
    currency               VARCHAR(3)               NOT NULL DEFAULT 'USD',
    note                   VARCHAR(4000)            NOT NULL DEFAULT '',
    txn_time               VARCHAR(8)               NOT NULL DEFAULT '',
    source_account         VARCHAR(100)             NOT NULL DEFAULT '',
    income_source_id       VARCHAR(64)              NOT NULL DEFAULT '',
    commitment_id          VARCHAR(64)              NOT NULL DEFAULT '',
    schedule_line_id       VARCHAR(64)              NOT NULL DEFAULT '',
    external_id            VARCHAR(255)             NOT NULL DEFAULT '',
    include_in_utilization BOOLEAN                  NOT NULL DEFAULT FALSE,
    budget_id              VARCHAR(64)              NOT NULL DEFAULT '',
    budget_category_id     VARCHAR(64)              NOT NULL DEFAULT '',
    created_at             TIMESTAMP WITH TIME ZONE,
    updated_at             TIMESTAMP WITH TIME ZONE
);
CREATE INDEX ix_fin_txn_user_month ON fin_transactions (user_id, txn_month);
CREATE INDEX ix_fin_txn_budget ON fin_transactions (budget_id);
CREATE INDEX ix_fin_txn_external ON fin_transactions (user_id, external_id);

CREATE TABLE fin_merchant_links (
    id          VARCHAR(64)  PRIMARY KEY,
    keyword     VARCHAR(120) NOT NULL,
    category_id VARCHAR(64)  NOT NULL,
    user_id     VARCHAR(64)
);
CREATE INDEX ix_fin_merchant_links_user ON fin_merchant_links (user_id);

CREATE TABLE fin_budgets (
    id           VARCHAR(64)    PRIMARY KEY,
    user_id      VARCHAR(64)    NOT NULL,
    category_id  VARCHAR(64)    NOT NULL DEFAULT '',
    group_id     VARCHAR(64)    NOT NULL DEFAULT '',
    period_year  INTEGER        NOT NULL,
    period_month INTEGER        NOT NULL,
    forecast     NUMERIC(14, 2) NOT NULL DEFAULT 0
);
CREATE INDEX ix_fin_budgets_user_period ON fin_budgets (user_id, period_year, period_month);

CREATE TABLE fin_savings (
    id           VARCHAR(64)    PRIMARY KEY,
    user_id      VARCHAR(64)    NOT NULL,
    period_year  INTEGER        NOT NULL,
    period_month INTEGER        NOT NULL,
    actual       NUMERIC(14, 2),
    target       NUMERIC(14, 2) NOT NULL DEFAULT 0,
    goal_status  VARCHAR(20)    NOT NULL DEFAULT 'pending'
);
CREATE INDEX ix_fin_savings_user ON fin_savings (user_id);

CREATE TABLE fin_commitments (
    id                   VARCHAR(64)              PRIMARY KEY,
    user_id              VARCHAR(64)              NOT NULL,
    name                 VARCHAR(200)             NOT NULL,
    amount               NUMERIC(14, 2)           NOT NULL DEFAULT 0,
    start_date           DATE,
    term_months          INTEGER                  NOT NULL DEFAULT 0,
    frequency            VARCHAR(20)              NOT NULL DEFAULT 'monthly',
    payment_amount       NUMERIC(14, 2)           NOT NULL DEFAULT 0,
    balloon              NUMERIC(14, 2)           NOT NULL DEFAULT 0,
    currency             VARCHAR(3)               NOT NULL DEFAULT 'USD',
    reminder_enabled     BOOLEAN                  NOT NULL DEFAULT TRUE,
    reminder_days_before INTEGER                  NOT NULL DEFAULT 3,
    created_at           TIMESTAMP WITH TIME ZONE,
    updated_at           TIMESTAMP WITH TIME ZONE
);
CREATE INDEX ix_fin_commitments_user ON fin_commitments (user_id);

CREATE TABLE fin_schedule_lines (
    id            VARCHAR(64)    PRIMARY KEY,
    commitment_id VARCHAR(64)    NOT NULL,
    due_date      DATE,
    amount        NUMERIC(14, 2) NOT NULL DEFAULT 0,
    status        VARCHAR(20)    NOT NULL DEFAULT 'outstanding',
    seq_no        INTEGER        NOT NULL DEFAULT 0,
    paid_date     DATE,
    reminder_sent BOOLEAN        NOT NULL DEFAULT FALSE
);
CREATE INDEX ix_fin_schedule_commitment ON fin_schedule_lines (commitment_id);

CREATE TABLE fin_financial_standings (
    id                     VARCHAR(64)              PRIMARY KEY,
    user_id                VARCHAR(64)              NOT NULL,
    snapshot_date          DATE,
    total_assets           NUMERIC(14, 2)           NOT NULL DEFAULT 0,
    current_assets         NUMERIC(14, 2)           NOT NULL DEFAULT 0,
    fixed_assets           NUMERIC(14, 2)           NOT NULL DEFAULT 0,
    total_liabilities      NUMERIC(14, 2)           NOT NULL DEFAULT 0,
    short_term_liabilities NUMERIC(14, 2)           NOT NULL DEFAULT 0,
    long_term_liabilities  NUMERIC(14, 2)           NOT NULL DEFAULT 0,
    notes                  VARCHAR(4000)            NOT NULL DEFAULT '',
    created_at             TIMESTAMP WITH TIME ZONE
);
CREATE INDEX ix_fin_standings_user ON fin_financial_standings (user_id);

CREATE TABLE fin_type_category_maps (
    id               VARCHAR(64) PRIMARY KEY,
    user_id          VARCHAR(64),
    consumption_type VARCHAR(32) NOT NULL DEFAULT 'other',
    category_id      VARCHAR(64) NOT NULL
);

CREATE TABLE fin_thresholds (
    id            VARCHAR(64)   PRIMARY KEY,
    user_id       VARCHAR(64)   NOT NULL,
    category_id   VARCHAR(64),
    warn_pct      NUMERIC(5, 1) NOT NULL DEFAULT 80,
    critical_pct  NUMERIC(5, 1) NOT NULL DEFAULT 100,
    email_enabled BOOLEAN       NOT NULL DEFAULT TRUE
);
CREATE INDEX ix_fin_thresholds_user ON fin_thresholds (user_id);

CREATE TABLE fin_accounts (
    id                   VARCHAR(64)  PRIMARY KEY,
    user_id              VARCHAR(64)  NOT NULL,
    name                 VARCHAR(120) NOT NULL,
    account_type         VARCHAR(20)  NOT NULL DEFAULT 'bank',
    sort_order           INTEGER      NOT NULL DEFAULT 0,
    active               BOOLEAN      NOT NULL DEFAULT TRUE,
    default_for_expenses BOOLEAN      NOT NULL DEFAULT FALSE
);
CREATE INDEX ix_fin_accounts_user ON fin_accounts (user_id);

CREATE TABLE fin_alerts (
    id               VARCHAR(64)              PRIMARY KEY,
    user_id          VARCHAR(64)              NOT NULL,
    period_year      INTEGER                  NOT NULL,
    period_month     INTEGER                  NOT NULL,
    category_id      VARCHAR(120)             NOT NULL DEFAULT '',
    severity         VARCHAR(20)              NOT NULL DEFAULT 'WARN',
    title            VARCHAR(200)             NOT NULL DEFAULT '',
    description      VARCHAR(4000)            NOT NULL DEFAULT '',
    alert_type       VARCHAR(32)              NOT NULL DEFAULT 'utilization',
    utilization_pct  NUMERIC(8, 2),
    actual           NUMERIC(14, 2)           NOT NULL DEFAULT 0,
    forecast         NUMERIC(14, 2)           NOT NULL DEFAULT 0,
    commitment_id    VARCHAR(64)              NOT NULL DEFAULT '',
    schedule_line_id VARCHAR(64)              NOT NULL DEFAULT '',
    due_date         VARCHAR(32)              NOT NULL DEFAULT '',
    commitment_name  VARCHAR(200)             NOT NULL DEFAULT '',
    is_resolved      BOOLEAN                  NOT NULL DEFAULT FALSE,
    resolution       VARCHAR(16)              NOT NULL DEFAULT '',
    resolved_at      TIMESTAMP WITH TIME ZONE,
    snoozed_until    TIMESTAMP WITH TIME ZONE,
    email_sent       BOOLEAN                  NOT NULL DEFAULT FALSE,
    fingerprint      VARCHAR(255)             NOT NULL DEFAULT '',
    created_at       TIMESTAMP WITH TIME ZONE,
    updated_at       TIMESTAMP WITH TIME ZONE
);
CREATE INDEX ix_fin_alerts_user ON fin_alerts (user_id);

CREATE TABLE fin_personal_budgets (
    id           VARCHAR(64)              PRIMARY KEY,
    user_id      VARCHAR(64)              NOT NULL,
    name         VARCHAR(120)             NOT NULL,
    description  VARCHAR(4000)            NOT NULL DEFAULT '',
    currency     VARCHAR(3)               NOT NULL DEFAULT 'USD',
    start_date   DATE,
    end_date     DATE,
    total_amount NUMERIC(14, 2)           NOT NULL DEFAULT 0,
    status       VARCHAR(20)              NOT NULL DEFAULT 'draft',
    project_tag  VARCHAR(80)              NOT NULL DEFAULT '',
    notes        VARCHAR(4000)            NOT NULL DEFAULT '',
    is_default   BOOLEAN                  NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMP WITH TIME ZONE,
    updated_at   TIMESTAMP WITH TIME ZONE
);
CREATE INDEX ix_fin_personal_budgets_user ON fin_personal_budgets (user_id);

CREATE TABLE fin_personal_budget_categories (
    id               VARCHAR(64)    PRIMARY KEY,
    budget_id        VARCHAR(64)    NOT NULL,
    name             VARCHAR(120)   NOT NULL,
    allocated_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
    sort_order       INTEGER        NOT NULL DEFAULT 0,
    notes            VARCHAR(4000)  NOT NULL DEFAULT '',
    group_id         VARCHAR(64)    NOT NULL DEFAULT '',
    category_id      VARCHAR(64)    NOT NULL DEFAULT '',
    parent_id        VARCHAR(64)    NOT NULL DEFAULT ''
);
CREATE INDEX ix_fin_pb_categories_budget ON fin_personal_budget_categories (budget_id);

CREATE TABLE fin_personal_budget_members (
    id         VARCHAR(64)              PRIMARY KEY,
    budget_id  VARCHAR(64)              NOT NULL,
    user_id    VARCHAR(64)              NOT NULL,
    role       VARCHAR(20)              NOT NULL DEFAULT 'viewer',
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX ix_fin_pb_members_budget ON fin_personal_budget_members (budget_id);
CREATE INDEX ix_fin_pb_members_user ON fin_personal_budget_members (user_id);

CREATE TABLE fin_personal_budget_notifications (
    id           VARCHAR(64)              PRIMARY KEY,
    recipient_id VARCHAR(64)              NOT NULL,
    budget_id    VARCHAR(64)              NOT NULL,
    shared_by_id VARCHAR(64)              NOT NULL,
    role         VARCHAR(20)              NOT NULL DEFAULT 'viewer',
    title        VARCHAR(200)             NOT NULL,
    message      VARCHAR(4000)            NOT NULL DEFAULT '',
    read_at      TIMESTAMP WITH TIME ZONE,
    created_at   TIMESTAMP WITH TIME ZONE
);
CREATE INDEX ix_fin_pb_notifications_recipient ON fin_personal_budget_notifications (recipient_id);

CREATE TABLE fin_personal_budget_invites (
    id            VARCHAR(64)              PRIMARY KEY,
    budget_id     VARCHAR(64)              NOT NULL,
    email         VARCHAR(254)             NOT NULL,
    role          VARCHAR(20)              NOT NULL DEFAULT 'viewer',
    invited_by_id VARCHAR(64)              NOT NULL,
    created_at    TIMESTAMP WITH TIME ZONE,
    updated_at    TIMESTAMP WITH TIME ZONE
);
CREATE INDEX ix_fin_pb_invites_budget ON fin_personal_budget_invites (budget_id);
CREATE INDEX ix_fin_pb_invites_email ON fin_personal_budget_invites (email);

CREATE TABLE fin_income_streams (
    id         VARCHAR(64)              PRIMARY KEY,
    user_id    VARCHAR(64)              NOT NULL,
    name       VARCHAR(120)             NOT NULL,
    amount     NUMERIC(14, 2)           NOT NULL DEFAULT 0,
    currency   VARCHAR(3)               NOT NULL DEFAULT 'USD',
    frequency  VARCHAR(16)              NOT NULL DEFAULT 'monthly',
    account_id VARCHAR(64)              NOT NULL DEFAULT '',
    active     BOOLEAN                  NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX ix_fin_income_streams_user ON fin_income_streams (user_id);

CREATE TABLE fin_group_buckets (
    id         VARCHAR(64)              PRIMARY KEY,
    user_id    VARCHAR(64)              NOT NULL,
    group_id   VARCHAR(64)              NOT NULL,
    bucket     VARCHAR(16)              NOT NULL DEFAULT 'wants',
    created_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX ix_fin_group_buckets_user ON fin_group_buckets (user_id);

CREATE TABLE fin_budget_plans (
    id                VARCHAR(64)              PRIMARY KEY,
    user_id           VARCHAR(64)              NOT NULL,
    period_year       INTEGER                  NOT NULL,
    period_month      INTEGER                  NOT NULL,
    plan_type         VARCHAR(32)              NOT NULL,
    status            VARCHAR(16)              NOT NULL DEFAULT 'suggested',
    reason            VARCHAR(32)              NOT NULL DEFAULT 'manual',
    currency          VARCHAR(3)               NOT NULL DEFAULT 'USD',
    income_total      NUMERIC(14, 2)           NOT NULL DEFAULT 0,
    commitments_total NUMERIC(14, 2)           NOT NULL DEFAULT 0,
    available         NUMERIC(14, 2)           NOT NULL DEFAULT 0,
    needs_total       NUMERIC(14, 2)           NOT NULL DEFAULT 0,
    wants_total       NUMERIC(14, 2)           NOT NULL DEFAULT 0,
    savings_amount    NUMERIC(14, 2)           NOT NULL DEFAULT 0,
    lines_json        VARCHAR(100000)          NOT NULL DEFAULT '[]',
    warnings_json     VARCHAR(20000)           NOT NULL DEFAULT '[]',
    accepted_at       TIMESTAMP WITH TIME ZONE,
    created_at        TIMESTAMP WITH TIME ZONE
);
CREATE INDEX ix_fin_budget_plans_user ON fin_budget_plans (user_id, period_year, period_month);
