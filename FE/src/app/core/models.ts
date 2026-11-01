export interface User {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  timezone?: string;
  country?: string;
  default_currency?: string;
  email_verified?: boolean;
  /** Email + in-app suggestions when income, commitments or spending change */
  notify_plan_updates?: boolean;
  /** Share of income the planner aims to save */
  savings_target_pct?: number;
  /** Support admin: can open the Admin area */
  is_staff?: boolean;
  /** Can also grant / remove the admin role */
  is_superuser?: boolean;
}

export interface UserPreferences {
  timezone: string;
  country: string;
  default_currency: string;
}

export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface AuthResponse extends AuthTokens {
  user?: User;
}

export interface RegisterResponse {
  detail: string;
  email?: string;
  email_sent?: boolean;
  verification_required?: boolean;
  user?: User;
  access?: string;
  refresh?: string;
}

export interface Expense {
  id: string;
  date: string;
  time?: string;
  amount: string;
  currency: string;
  amount_usd: string;
  consumption_type: string;
  category_id?: string | null;
  category_name?: string;
  note: string;
  description?: string;
  direction?: string;
  country: string;
  record_status: string;
  created_at?: string;
  modified_at?: string;
}


export interface ExpenseSummary {
  year: number;
  month: number;
  month_name: string;
  report_currency?: string;
  total?: number;
  total_usd: number;
  count: number;
  breakdown: { type: string; amount?: number; amount_usd: number; percent: number }[];
}

export interface MetaData {
  currencies: { code: string; label: string }[];
  consumption_types: { code: string; label: string }[];
  countries: { code: string; label: string }[];
  suggested?: UserPreferences;
  saved_preferences?: UserPreferences;
  exchange_rates?: Record<string, number>;
}

/** Synthetic category for expenses whose consumption_type has no TypeCategoryMap. */
export const UNMAPPED_CATEGORY_ID = '_unmapped_';

export interface BudgetAlert {
  id: string;
  severity: string;
  title: string;
  description: string;
  /** utilization | commitment_due | risk */
  alert_type?: string;
  year: number;
  month: number;
  category_id: string;
  utilization_pct: string | null;
  actual: string;
  forecast: string;
  is_resolved: boolean;
  state?: AlertState;
  /** user = resolved by you; auto = condition cleared */
  resolution?: '' | 'user' | 'auto';
  resolved_at?: string | null;
  snoozed_until?: string | null;
  created_at?: string | null;
  commitment_id?: string;
  schedule_line_id?: string;
  due_date?: string;
  commitment_name?: string;
}

export type AlertState = 'open' | 'snoozed' | 'resolved';
export type AlertTab = AlertState | 'all';
export type AlertBulkAction = 'resolve' | 'reopen' | 'snooze' | 'unsnooze';

export interface AlertCounts {
  /** Badge number: open and not snoozed */
  count: number;
  open: number;
  snoozed: number;
  resolved: number;
  all: number;
}

export interface UtilizationRow {
  category_id: string;
  category_name: string;
  group_name: string;
  forecast: string;
  actual: string;
  remaining: string;
  variance: string;
  utilization_pct: string | null;
  status: string;
  warn_pct: string;
  critical_pct: string;
  email_enabled?: boolean;
  include_in_total?: boolean;
  row_type?: string;
  parent_group_id?: string;
}

export interface UtilizationReport {
  report_currency?: string;
  rows: UtilizationRow[];
  total_forecast: string;
  total_actual: string;
  overall_variance: string;
  overall_util: string | null;
  overall_status: string;
  remaining: string;
}

export interface BudgetDashboard {
  year: number;
  month: number;
  report_currency?: string;
  report: UtilizationReport;
  income_total: string;
  expense_total: string;
  open_alerts: BudgetAlert[];
}

export interface YearlyMonthRow {
  month: number;
  month_name: string;
  month_short: string;
  income_total: string;
  expense_total: string;
  net: string;
  total_forecast: string;
  total_actual: string;
  remaining: string;
  overall_util: string | null;
  overall_status: string;
}

export interface YearlyOverview {
  year: number;
  report_currency?: string;
  income_total: string;
  expense_total: string;
  net: string;
  months: YearlyMonthRow[];
}

export interface Transaction {
  id: string;
  date: string;
  time?: string;
  month: string;
  description: string;
  category_id: string | null;
  classification: string | null;
  amount: string;
  currency?: string;
  note?: string;
  direction: string;
  source_account: string;
  account_id?: string;
  /** @deprecated use account_id */
  income_source_id?: string;
  commitment_id?: string;
  schedule_line_id?: string;
  external_id: string;
  budget_id?: string;
  budget_category_id?: string;
  /** Transfers: destination account (one-row transfer). Empty for legacy two-row transfers. */
  to_account_id?: string;
  /** Pending income does not count until settled; pending expenses count right away. */
  status?: TransactionStatus;
}

export type TransactionStatus = 'settled' | 'pending';

export type AccountType = 'bank' | 'credit_card' | 'wallet' | 'other';

export interface AccountBalance {
  account_id: string;
  name: string;
  account_type: AccountType;
  is_active: boolean;
  /** Balance per currency, e.g. { USD: "120.00", LBP: "-5000.00" } */
  balances: Record<string, string>;
  /** All currencies converted to `currency` */
  total: string;
  currency: string;
}

export interface AccountBalancesResponse {
  currency: string;
  accounts: AccountBalance[];
}

export type PlannedItemKind = 'income' | 'expense';
export type PlannedItemFrequency = 'once' | 'weekly' | 'biweekly' | 'monthly' | 'yearly';

export interface PlannedItem {
  id: string;
  name: string;
  kind: PlannedItemKind;
  amount: string;
  currency: string;
  frequency: PlannedItemFrequency;
  start_date: string;
  end_date: string | null;
  account_id: string;
  category_id: string;
  is_essential: boolean;
  is_active: boolean;
  monthly_amount: string;
}

export type PlannedItemPayload = Partial<Omit<PlannedItem, 'id' | 'monthly_amount'>>;

export interface PlannedItemList {
  items: PlannedItem[];
  currency: string;
  monthly_income: string;
  monthly_expense: string;
}

export type RiskStatus = 'ok' | 'warn' | 'high' | 'unknown';
export type RiskLevel = 'low' | 'medium' | 'high' | 'unknown';

export interface RiskFactor {
  key: string;
  category: 'debt' | 'liquidity';
  label: string;
  value: string | null;
  /** pct | count | months | money */
  unit: string;
  status: RiskStatus;
  warn_at: string | null;
  high_at: string | null;
  explanation: string;
  recommendation: string;
  items: Array<Record<string, unknown>>;
}

export interface RiskReport {
  as_of: string;
  currency: string;
  score: number | null;
  level: RiskLevel;
  factors: RiskFactor[];
  missing: string[];
  inputs: Record<string, string | string[] | null>;
  thresholds: Record<string, string>;
}

export interface RiskHistoryPoint {
  as_of: string;
  score: number | null;
  level: RiskLevel;
}

export type RiskThresholdKey =
  | 'dti_warn'
  | 'dti_high'
  | 'balloon_warn'
  | 'balloon_high'
  | 'debt_assets_warn'
  | 'debt_assets_high'
  | 'emergency_warn_months'
  | 'emergency_high_months'
  | 'cash_flow_warn_pct'
  | 'horizon_months';

export interface RiskSettings {
  /** null = using the default */
  overrides: Record<RiskThresholdKey, string | null>;
  effective: Record<RiskThresholdKey, string>;
  defaults: Record<RiskThresholdKey, string>;
  included_account_ids: string[];
  alerts_enabled: boolean;
  email_enabled: boolean;
}

export type RiskSettingsPatch = Partial<Record<RiskThresholdKey, string | number | null>> & {
  included_account_ids?: string[];
  alerts_enabled?: boolean;
  email_enabled?: boolean;
};

export interface Account {
  id: string;
  name: string;
  account_type: AccountType;
  order: number;
  is_active: boolean;
  is_default_for_expenses?: boolean;
}

/** @deprecated use Account */
export type IncomeSource = Account;

export interface BudgetGroup {
  id: string;
  name: string;
  order: number;
  /** Shared default (read-only unless you are an admin) */
  is_shared?: boolean;
  can_edit?: boolean;
}

export interface BudgetCategory {
  id: string;
  name: string;
  group_id: string;
  group_name: string;
  include_in_reports: boolean;
  order: number;
  /** Shared default (read-only unless you are an admin) */
  is_shared?: boolean;
  can_edit?: boolean;
}

export interface CategoryGroupResponse {
  groups: BudgetGroup[];
  categories: BudgetCategory[];
}

export interface BudgetSubRow {
  category_id: string;
  category_name: string;
  forecast: string;
  actual: string;
}

export interface BudgetRow {
  group_id?: string | null;
  category_id?: string | null;
  category_name: string;
  forecast: string;
  forecast_explicit?: string | null;
  forecast_from_subs?: string;
  forecast_is_derived?: boolean;
  actual: string;
  include_in_total?: boolean;
  row_type?: string;
  sub_budgets?: BudgetSubRow[];
}

export type PersonalBudgetStatus = 'draft' | 'active' | 'completed' | 'archived';

export interface PersonalBudget {
  id: string;
  user_id: string;
  name: string;
  description: string;
  currency: string;
  start_date: string | null;
  end_date: string | null;
  total_amount: string;
  status: PersonalBudgetStatus;
  project_tag: string;
  notes: string;
  is_default: boolean;
  /** Sub-budget of the monthly plan: money reserved in the plan; its expenses count only here. */
  in_plan?: boolean;
  /** First month the plan reserves money for it (YYYY-MM-01) */
  funding_start?: string | null;
  /** Number of months the total is spread over */
  funding_months?: number;
  /** This month's reserved share, in the budget's currency */
  monthly_contribution?: string;
  /** Expenses tagged to this budget */
  transactions_count?: number;
  spent: string;
  remaining: string;
  percent_used: number;
  created_at: string | null;
  updated_at: string | null;
  access_role?: 'owner' | 'viewer' | 'editor';
  is_owner?: boolean;
  owner?: PersonalBudgetUserRef;
  can_edit?: boolean;
  can_share?: boolean;
}

export interface PersonalBudgetCategory {
  id: string;
  budget_id: string;
  name: string;
  allocated_amount: string;
  spent: string;
  remaining: string;
  order: number;
  notes: string;
  group_id?: string;
  category_id?: string;
  parent_id?: string;
  sub_categories?: PersonalBudgetCategory[];
}

export interface PersonalBudgetTransaction {
  id: string;
  date: string | null;
  description: string;
  amount: string;
  currency: string;
  direction: string;
  budget_category_id: string;
  note: string;
}

export interface PersonalBudgetDashboard {
  total_budgets: number;
  active_budgets: number;
  total_allocated: string;
  total_spent: string;
  total_remaining: string;
  budgets: PersonalBudget[];
  shared_with_me?: PersonalBudget[];
}

export interface PersonalBudgetUserRef {
  id: number;
  email: string;
  name: string;
  username?: string;
}

export interface PersonalBudgetMember {
  id: string;
  user_id?: string;
  email: string;
  name?: string;
  role: 'viewer' | 'editor';
  pending?: boolean;
  created_at: string | null;
}

export interface PersonalBudgetPendingInvite {
  id: string;
  email: string;
  role: 'viewer' | 'editor';
  pending: true;
  created_at: string | null;
}

export interface PersonalBudgetAccessList {
  owner: PersonalBudgetUserRef;
  members: PersonalBudgetMember[];
  pending_invites?: PersonalBudgetPendingInvite[];
  result?: 'shared' | 'invited';
  email_sent?: boolean;
  invited_email?: string;
}

export interface PersonalBudgetNotification {
  id: string;
  budget_id: string;
  budget_name: string;
  title: string;
  message: string;
  role: string;
  shared_by: PersonalBudgetUserRef | null;
  read: boolean;
  created_at: string | null;
}

export interface PersonalBudgetDetail extends PersonalBudget {
  categories?: PersonalBudgetCategory[];
  categories_allocated_total?: string;
  transactions?: PersonalBudgetTransaction[];
}

export interface PersonalBudgetListResponse {
  budgets: PersonalBudget[];
  shared_with_me?: PersonalBudget[];
  statuses: PersonalBudgetStatus[];
}

export interface SavingsRow {
  year: number;
  month: number;
  target: string;
  actual: string;
  goal_status: string;
  goal_status_display?: string;
}

export interface Commitment {
  id: string;
  name: string;
  amount: string;
  currency?: string;
  start_date: string | null;
  term_months: number;
  frequency: string;
  payment_amount: string;
  balloon: string;
  remaining_principal: string;
  reminder_enabled?: boolean;
  reminder_days_before?: number;
  payments_total?: number;
  payments_completed?: number;
  payments_remaining?: number;
  next_due_date?: string | null;
  next_due_amount?: string;
  next_due_line_id?: string | null;
  upcoming_count?: number;
  overdue_count?: number;
  schedule?: CommitmentScheduleLine[];
}

export interface CommitmentScheduleLine {
  id: string;
  commitment_id: string;
  sequence: number;
  due_date: string | null;
  payment_date?: string | null;
  paid_date: string | null;
  amount: string;
  status: string;
  reminder_sent: boolean;
  is_overdue: boolean;
  days_until_due: number | null;
}

export interface FinancialStanding {
  id: string;
  snapshot_date: string | null;
  total_assets: string;
  current_assets: string;
  fixed_assets: string;
  total_liabilities: string;
  short_term_liabilities: string;
  long_term_liabilities: string;
  notes: string;
}

export interface MerchantLink {
  id: string;
  keyword: string;
  category_id: string;
  category_name?: string;
  group_id?: string;
  group_name?: string;
}

export interface UnmatchedMerchant {
  merchant: string;
  keyword_suggestion: string;
  count: number;
  transaction_ids: string[];
  sample_descriptions: string[];
}

export interface TransactionUploadResult {
  created: number;
  skipped: number;
  matched: number;
  unmatched_count: number;
  unmatched: UnmatchedMerchant[];
  /** Format actually used (auto resolves to dmy/mdy) */
  date_format?: ImportDateFormat;
  currency?: string;
  errors?: { row: number; error: string }[];
}

export type ImportDateFormat = 'auto' | 'dmy' | 'mdy' | 'ymd';

export interface TransactionImportOptions {
  dateFormat?: ImportDateFormat;
  currency?: string;
  accountId?: string;
}

export interface TypeMapRow {
  consumption_type: string;
  category_id: string;
  category_name: string;
  group_id?: string;
  group_name?: string;
}

export interface ThresholdRow {
  id: string;
  category_id: string | null;
  category_name: string;
  warn_pct: string;
  critical_pct: string;
  email_enabled: boolean;
}

// ---- Budget planning ----

export type IncomeFrequency = 'monthly' | 'biweekly' | 'weekly' | 'yearly';
export type PlanType = 'rule_50_30_20' | 'spending_based';
export type PlanBucket = 'needs' | 'wants' | 'savings';
export type PlanStatus = 'suggested' | 'accepted' | 'dismissed' | 'superseded';

export interface IncomeStream {
  id: string;
  name: string;
  amount: string;
  currency: string;
  frequency: IncomeFrequency;
  monthly_amount: string;
  account_id: string;
  is_active: boolean;
}

export interface IncomeStreamList {
  streams: IncomeStream[];
  currency: string;
  monthly_total: string;
}

export interface PlanLine {
  group_id: string;
  group_name: string;
  bucket: PlanBucket;
  amount: string;
  average_spend: string;
  current_forecast: string;
  /** rule | history | trimmed | edited */
  basis: string;
}

export interface BudgetPlan {
  id?: string;
  year: number;
  month: number;
  plan_type: PlanType;
  effective_type?: PlanType;
  label: string;
  status?: PlanStatus;
  reason?: string;
  currency: string;
  income_total: string;
  commitments_total: string;
  commitments?: { commitment_id: string; name: string; amount: string }[];
  available: string;
  needs_total: string;
  wants_total: string;
  invested_total: string;
  savings_amount: string;
  savings_pct: number;
  history_months?: number;
  lines: PlanLine[];
  /** Trips / projects reserved inside this month's available money */
  sub_budgets?: PlanSubBudget[];
  reserved_total?: string;
  warnings: string[];
  created_at?: string | null;
  accepted_at?: string | null;
}

export interface PlanSubBudget {
  budget_id: string;
  name: string;
  /** Reserved this month (plan currency) */
  amount: string;
  total: string;
  funded_before: string;
  spent: string;
  start_date: string | null;
  end_date: string | null;
  funding_months: number;
}

export interface PlanPreview {
  year: number;
  month: number;
  currency: string;
  plans: BudgetPlan[];
}

export interface PlanBucketRow {
  group_id: string;
  group_name: string;
  bucket: PlanBucket;
  is_default: boolean;
}

export interface AppNotification {
  id: string;
  kind: string;
  title: string;
  body: string;
  link: string;
  related_id: string;
  is_read: boolean;
  created_at: string | null;
}

// ---- Help & support / Admin ----------------------------------------------------

/** open: support must act (unassigned = pool) · waiting_user: support asked something · resolved: user must confirm */
export type TicketStatus = 'open' | 'waiting_user' | 'resolved' | 'closed';
export type TicketCategory = 'account' | 'bug' | 'data' | 'other';

export interface UserRef {
  id: number;
  username: string;
  email: string;
}

export interface TicketMessage {
  id: number;
  body: string;
  from_staff: boolean;
  /** Automatic note such as "Closed: the user confirmed…" */
  system?: boolean;
  author: string;
  created_at: string;
}

export interface SupportTicket {
  id: number;
  subject: string;
  category: TicketCategory;
  status: TicketStatus;
  priority: 'normal' | 'high';
  created_at: string;
  updated_at: string;
  last_staff_reply_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  /** user_confirmed | auto | '' */
  close_reason: string;
  /** Staff views only */
  user?: UserRef;
  assigned_to?: UserRef | null;
  assigned_at?: string | null;
  messages?: TicketMessage[];
}

export type AssignmentMode = 'least_busy' | 'round_robin' | 'pool';

export interface SupportSettings {
  assignment_mode: AssignmentMode;
  assignment_modes: { value: AssignmentMode; label: string }[];
  /** 0 = off */
  reminder_days: number;
  /** 0 = off */
  auto_close_days: number;
  email_admins: boolean;
  /** false = still using the .env defaults */
  saved: boolean;
  updated_by: UserRef | null;
  updated_at: string | null;
}

export interface IssueFlag {
  code: string;
  /** high | warn | info */
  severity: string;
  text: string;
}

export interface AdminUserRow {
  id: number;
  username: string;
  email: string;
  name: string;
  is_active: boolean;
  is_staff: boolean;
  is_superuser: boolean;
  email_verified: boolean;
  date_joined: string | null;
  last_login: string | null;
  flags: IssueFlag[];
}

export interface Paged<T> {
  count: number;
  page: number;
  page_size: number;
  results: T[];
}

export interface AdminOverview {
  users_total: number;
  users_new_7d: number;
  email_unverified: number;
  setup_stuck: number;
  deactivated: number;
  tickets_open: number;
  tickets_waiting_user: number;
  tickets_pool: number;
  tickets_resolved: number;
  my_open_tickets: number;
  emails_failed_7d: number;
}

export interface EmailLogRow {
  to: string;
  subject: string;
  kind: 'account' | 'notification';
  status: 'sent' | 'failed' | 'console';
  error: string;
  created_at: string;
}

export interface AdminUserDetail {
  user: UserRef & {
    name: string;
    is_active: boolean;
    is_staff: boolean;
    is_superuser: boolean;
    date_joined: string | null;
    last_login: string | null;
    email_verified: boolean;
    email_verified_at: string | null;
    setup_status: string;
    setup_completed_at: string | null;
    notify_low_balance: boolean;
    has_password: boolean;
  };
  flags: IssueFlag[];
  emails: EmailLogRow[];
  tickets: SupportTicket[];
  currency?: string;
  accounts?: AccountBalance[];
  recent_transactions?: Transaction[];
  transactions_count?: number;
  commitments_count?: number;
  open_alerts?: BudgetAlert[];
  risk?: { as_of: string; score: number | null; level: string } | null;
  finance_error?: string;
}

export interface AuditLogRow {
  id: number;
  action: string;
  actor: UserRef | null;
  target_user: UserRef | null;
  ticket_id: number | null;
  detail: Record<string, unknown>;
  created_at: string;
}

export type AdminUserAction =
  | 'resend-verification'
  | 'mark-verified'
  | 'send-password-reset'
  | 'deactivate'
  | 'reactivate';
