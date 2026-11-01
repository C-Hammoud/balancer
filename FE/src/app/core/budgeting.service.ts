import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import {
  AppNotification,
  BudgetPlan,
  IncomeStream,
  IncomeStreamList,
  PlanBucket,
  PlanBucketRow,
  PlanPreview,
  PlanType,
  AlertBulkAction,
  AlertCounts,
  AlertTab,
  BudgetAlert,
  BudgetCategory,
  BudgetDashboard,
  BudgetGroup,
  BudgetRow,
  CategoryGroupResponse,
  Commitment,
  CommitmentScheduleLine,
  FinancialStanding,
  Account,
  IncomeSource,
  MerchantLink,
  PersonalBudget,
  PersonalBudgetDashboard,
  PersonalBudgetDetail,
  PersonalBudgetListResponse,
  PersonalBudgetAccessList,
  PersonalBudgetMember,
  PersonalBudgetNotification,
  PersonalBudgetUserRef,
  SavingsRow,
  ThresholdRow,
  Transaction,
  TransactionImportOptions,
  TransactionUploadResult,
  TypeMapRow,
  UtilizationReport,
  YearlyOverview,
} from './models';

@Injectable({ providedIn: 'root' })
export class BudgetingService {
  private readonly api = `${environment.apiUrl}/budgeting`;

  constructor(private http: HttpClient) {}

  dashboard(year: number, month: number): Observable<BudgetDashboard> {
    const params = new HttpParams().set('year', year).set('month', month);
    return this.http.get<BudgetDashboard>(`${this.api}/dashboard/`, { params });
  }

  yearly(year: number): Observable<YearlyOverview> {
    const params = new HttpParams().set('year', year);
    return this.http.get<YearlyOverview>(`${this.api}/yearly/`, { params });
  }

  utilization(year: number, month: number): Observable<UtilizationReport> {
    const params = new HttpParams().set('year', year).set('month', month);
    return this.http.get<UtilizationReport>(`${this.api}/utilization/`, { params });
  }

  categories(): Observable<CategoryGroupResponse> {
    return this.http.get<CategoryGroupResponse>(`${this.api}/categories/`);
  }

  createGroup(payload: { name: string; order?: number }): Observable<BudgetGroup> {
    return this.http.post<BudgetGroup>(`${this.api}/config/groups/`, payload);
  }

  updateGroup(id: string, payload: Partial<{ name: string; order: number }>): Observable<BudgetGroup> {
    return this.http.patch<BudgetGroup>(`${this.api}/config/groups/${id}/`, payload);
  }

  deleteGroup(id: string) {
    return this.http.delete(`${this.api}/config/groups/${id}/`);
  }

  createCategory(payload: {
    name: string;
    group_id: string;
    include_in_reports?: boolean;
    order?: number;
  }): Observable<BudgetCategory> {
    return this.http.post<BudgetCategory>(`${this.api}/config/categories/`, payload);
  }

  updateCategory(
    id: string,
    payload: Partial<{
      name: string;
      group_id: string;
      include_in_reports: boolean;
      order: number;
    }>
  ): Observable<BudgetCategory> {
    return this.http.patch<BudgetCategory>(`${this.api}/config/categories/${id}/`, payload);
  }

  deleteCategory(id: string) {
    return this.http.delete(`${this.api}/config/categories/${id}/`);
  }

  transactions(month?: string): Observable<Transaction[]> {
    let params = new HttpParams();
    if (month) params = params.set('month', month);
    return this.http.get<Transaction[]>(`${this.api}/transactions/`, { params });
  }

  createTransaction(payload: Partial<Transaction>): Observable<Transaction> {
    return this.http.post<Transaction>(`${this.api}/transactions/`, payload);
  }

  updateTransaction(id: string, payload: Partial<Transaction>): Observable<Transaction> {
    return this.http.patch<Transaction>(`${this.api}/transactions/${id}/`, payload);
  }

  deleteTransaction(id: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/transactions/${id}/`);
  }

  uploadTransactions(file: File, opts: TransactionImportOptions = {}): Observable<TransactionUploadResult> {
    const form = new FormData();
    form.append('file', file);
    if (opts.dateFormat) form.append('date_format', opts.dateFormat);
    if (opts.currency) form.append('currency', opts.currency);
    if (opts.accountId) form.append('account_id', opts.accountId);
    return this.http.post<TransactionUploadResult>(`${this.api}/transactions/upload/`, form);
  }

  budgets(year: number, month: number): Observable<{ year: number; month: number; rows: BudgetRow[] }> {
    const params = new HttpParams().set('year', year).set('month', month);
    return this.http.get<{ year: number; month: number; rows: BudgetRow[] }>(`${this.api}/budgets/`, { params });
  }

  updateBudget(year: number, month: number, categoryId: string, forecast: string | number) {
    return this.http.patch(`${this.api}/budgets/${year}/${month}/${categoryId}/`, { forecast });
  }

  updateGroupBudget(year: number, month: number, groupId: string, forecast: string | number) {
    return this.http.patch(`${this.api}/budgets/${year}/${month}/group/${groupId}/`, { forecast });
  }

  personalBudgetDashboard(): Observable<PersonalBudgetDashboard> {
    return this.http.get<PersonalBudgetDashboard>(`${this.api}/personal-budgets/dashboard/`);
  }

  personalBudgets(params?: {
    search?: string;
    status?: string;
    sort?: string;
    period_start?: string;
    period_end?: string;
    /** true = plan sub-budgets only, false = standalone budgets only */
    in_plan?: boolean;
  }): Observable<PersonalBudgetListResponse> {
    let httpParams = new HttpParams();
    if (params?.search) httpParams = httpParams.set('search', params.search);
    if (params?.status) httpParams = httpParams.set('status', params.status);
    if (params?.sort) httpParams = httpParams.set('sort', params.sort);
    if (params?.in_plan !== undefined) httpParams = httpParams.set('in_plan', params.in_plan ? '1' : '0');
    if (params?.period_start) httpParams = httpParams.set('period_start', params.period_start);
    if (params?.period_end) httpParams = httpParams.set('period_end', params.period_end);
    return this.http.get<PersonalBudgetListResponse>(`${this.api}/personal-budgets/`, { params: httpParams });
  }

  personalBudget(id: string): Observable<PersonalBudgetDetail> {
    return this.http.get<PersonalBudgetDetail>(`${this.api}/personal-budgets/${id}/`);
  }

  createPersonalBudget(payload: Partial<PersonalBudget>): Observable<PersonalBudgetDetail> {
    return this.http.post<PersonalBudgetDetail>(`${this.api}/personal-budgets/`, payload);
  }

  updatePersonalBudget(id: string, payload: Partial<PersonalBudget>): Observable<PersonalBudgetDetail> {
    return this.http.patch<PersonalBudgetDetail>(`${this.api}/personal-budgets/${id}/`, payload);
  }

  deletePersonalBudget(id: string) {
    return this.http.delete(`${this.api}/personal-budgets/${id}/`);
  }

  clonePersonalBudget(
    id: string,
    payload: Partial<{ name: string; start_date: string; end_date: string; status: string }>
  ): Observable<PersonalBudgetDetail> {
    return this.http.post<PersonalBudgetDetail>(`${this.api}/personal-budgets/${id}/clone/`, payload);
  }

  createPersonalBudgetCategory(
    budgetId: string,
    payload: {
      name?: string;
      group_id?: string;
      allocated_amount: string | number;
      notes?: string;
      order?: number;
      subcategories?: Array<{ category_id: string; allocated_amount: string | number; name?: string }>;
    }
  ): Observable<PersonalBudgetDetail> {
    return this.http.post<PersonalBudgetDetail>(`${this.api}/personal-budgets/${budgetId}/categories/`, payload);
  }

  updatePersonalBudgetCategory(
    budgetId: string,
    categoryId: string,
    payload: Partial<{ name: string; allocated_amount: string | number; notes: string; order: number }>
  ): Observable<PersonalBudgetDetail> {
    return this.http.patch<PersonalBudgetDetail>(
      `${this.api}/personal-budgets/${budgetId}/categories/${categoryId}/`,
      payload
    );
  }

  deletePersonalBudgetCategory(budgetId: string, categoryId: string): Observable<PersonalBudgetDetail> {
    return this.http.delete<PersonalBudgetDetail>(
      `${this.api}/personal-budgets/${budgetId}/categories/${categoryId}/`
    );
  }

  lookupPersonalBudgetUser(email: string): Observable<{ found: boolean; user?: PersonalBudgetUserRef; detail?: string }> {
    const params = new HttpParams().set('email', email);
    return this.http.get<{ found: boolean; user?: PersonalBudgetUserRef; detail?: string }>(
      `${this.api}/personal-budgets/users/lookup/`,
      { params }
    );
  }

  personalBudgetMembers(budgetId: string): Observable<PersonalBudgetAccessList> {
    return this.http.get<PersonalBudgetAccessList>(`${this.api}/personal-budgets/${budgetId}/members/`);
  }

  sharePersonalBudget(budgetId: string, payload: { email: string; role: 'viewer' | 'editor' }) {
    return this.http.post<PersonalBudgetAccessList>(`${this.api}/personal-budgets/${budgetId}/members/`, payload);
  }

  updatePersonalBudgetMember(budgetId: string, memberId: string, role: 'viewer' | 'editor') {
    return this.http.patch<PersonalBudgetAccessList>(
      `${this.api}/personal-budgets/${budgetId}/members/${memberId}/`,
      { role }
    );
  }

  removePersonalBudgetMember(budgetId: string, memberId: string) {
    return this.http.delete<PersonalBudgetAccessList>(
      `${this.api}/personal-budgets/${budgetId}/members/${memberId}/`
    );
  }

  cancelPersonalBudgetInvite(budgetId: string, inviteId: string) {
    return this.http.delete<PersonalBudgetAccessList>(
      `${this.api}/personal-budgets/${budgetId}/invites/${inviteId}/`
    );
  }

  personalBudgetNotifications(): Observable<{ notifications: PersonalBudgetNotification[] }> {
    return this.http.get<{ notifications: PersonalBudgetNotification[] }>(
      `${this.api}/personal-budgets/notifications/`
    );
  }

  markPersonalBudgetNotificationRead(id: string) {
    return this.http.post(`${this.api}/personal-budgets/notifications/${id}/read/`, {});
  }

  savings(): Observable<SavingsRow[]> {
    return this.http.get<SavingsRow[]>(`${this.api}/savings/`);
  }

  updateSavings(year: number, month: number, payload: Partial<SavingsRow>) {
    return this.http.patch(`${this.api}/savings/${year}/${month}/`, payload);
  }

  commitments(): Observable<Commitment[]> {
    return this.http.get<Commitment[]>(`${this.api}/commitments/`);
  }

  commitment(id: string): Observable<Commitment> {
    return this.http.get<Commitment>(`${this.api}/commitments/${id}/`);
  }

  createCommitment(payload: Partial<Commitment>) {
    return this.http.post<{ id: string }>(`${this.api}/commitments/`, payload);
  }

  updateCommitment(id: string, payload: Partial<Commitment>) {
    return this.http.patch<{ id: string }>(`${this.api}/commitments/${id}/`, payload);
  }

  deleteCommitment(id: string) {
    return this.http.delete(`${this.api}/commitments/${id}/`);
  }

  commitmentSchedule(id: string): Observable<CommitmentScheduleLine[]> {
    return this.http.get<CommitmentScheduleLine[]>(`${this.api}/commitments/${id}/schedule/`);
  }

  markCommitmentPaid(commitmentId: string, lineId: string, payment_date?: string) {
    return this.http.post<CommitmentScheduleLine>(
      `${this.api}/commitments/${commitmentId}/schedule/${lineId}/pay/`,
      payment_date ? { payment_date, paid_date: payment_date } : {}
    );
  }

  unmarkCommitmentPaid(commitmentId: string, lineId: string) {
    return this.http.post<CommitmentScheduleLine>(
      `${this.api}/commitments/${commitmentId}/schedule/${lineId}/unpay/`,
      {}
    );
  }

  updateCommitmentScheduleLine(
    commitmentId: string,
    lineId: string,
    payload: Partial<{ due_date: string; payment_date: string | null; amount: string | number; status: string }>
  ) {
    return this.http.patch<CommitmentScheduleLine>(
      `${this.api}/commitments/${commitmentId}/schedule/${lineId}/`,
      payload
    );
  }

  regenerateCommitmentSchedule(id: string) {
    return this.http.post<{ id: string; payments_total: number; schedule: CommitmentScheduleLine[] }>(
      `${this.api}/commitments/${id}/regenerate-schedule/`,
      {}
    );
  }

  financialStanding(): Observable<FinancialStanding[]> {
    return this.http.get<FinancialStanding[]>(`${this.api}/financial-standing/`);
  }

  createFinancialStanding(payload: Partial<FinancialStanding>) {
    return this.http.post<{ id: string }>(`${this.api}/financial-standing/`, payload);
  }

  alerts(show: AlertTab = 'open', refresh = false): Observable<BudgetAlert[]> {
    let params = new HttpParams().set('show', show);
    if (refresh) params = params.set('refresh', '1');
    return this.http.get<BudgetAlert[]>(`${this.api}/alerts/`, { params });
  }

  alertCount(): Observable<AlertCounts> {
    return this.http.get<AlertCounts>(`${this.api}/alerts/count/`);
  }

  resolveAlert(id: string) {
    return this.http.post(`${this.api}/alerts/${id}/resolve/`, {});
  }

  reopenAlert(id: string) {
    return this.http.post<BudgetAlert>(`${this.api}/alerts/${id}/reopen/`, {});
  }

  snoozeAlert(id: string, days: number) {
    return this.http.post<BudgetAlert>(`${this.api}/alerts/${id}/snooze/`, { days });
  }

  unsnoozeAlert(id: string) {
    return this.http.delete<BudgetAlert>(`${this.api}/alerts/${id}/snooze/`);
  }

  bulkAlerts(action: AlertBulkAction, ids: string[], days?: number) {
    return this.http.post<{ action: AlertBulkAction; updated: string[]; failed: string[] }>(
      `${this.api}/alerts/bulk/`,
      days ? { action, ids, days } : { action, ids }
    );
  }

  recordCommitmentDue(
    alertId: string,
    categoryId: string,
    opts: { accountId?: string; paymentDate?: string } = {}
  ) {
    return this.http.post<{
      id: string;
      recorded: boolean;
      is_resolved: boolean;
      transaction?: Transaction;
    }>(`${this.api}/alerts/${alertId}/record-commitment/`, {
      record_expense: true,
      category_id: categoryId,
      ...(opts.accountId ? { account_id: opts.accountId } : {}),
      ...(opts.paymentDate ? { payment_date: opts.paymentDate } : {}),
    });
  }

  skipCommitmentDue(alertId: string) {
    return this.http.post<{ id: string; recorded: boolean; is_resolved: boolean }>(
      `${this.api}/alerts/${alertId}/record-commitment/`,
      { record_expense: false }
    );
  }

  typeMaps(): Observable<TypeMapRow[]> {
    return this.http.get<TypeMapRow[]>(`${this.api}/config/type-maps/`);
  }

  saveTypeMap(consumption_type: string, category_id: string) {
    return this.http.post(`${this.api}/config/type-maps/`, { consumption_type, category_id });
  }

  thresholds(): Observable<ThresholdRow[]> {
    return this.http.get<ThresholdRow[]>(`${this.api}/config/thresholds/`);
  }

  saveThreshold(payload: {
    category_id?: string | null;
    warn_pct: number | string;
    critical_pct: number | string;
    email_enabled: boolean;
  }) {
    return this.http.post(`${this.api}/config/thresholds/`, payload);
  }

  deleteThreshold(id: string) {
    return this.http.delete(`${this.api}/config/thresholds/${id}/`);
  }

  merchantLinks(): Observable<MerchantLink[]> {
    return this.http.get<MerchantLink[]>(`${this.api}/config/merchant-links/`);
  }

  createMerchantLink(
    keyword: string,
    category_id: string,
    opts?: { transaction_ids?: string[]; apply_unmatched?: boolean }
  ) {
    return this.http.post<{ id: string; created?: boolean; transactions_updated?: number }>(
      `${this.api}/config/merchant-links/`,
      {
        keyword,
        category_id,
        transaction_ids: opts?.transaction_ids || [],
        apply_unmatched: opts?.apply_unmatched ?? true,
      }
    );
  }

  deleteMerchantLink(id: string) {
    return this.http.delete(`${this.api}/config/merchant-links/${id}/`);
  }

  accounts(activeOnly = false): Observable<Account[]> {
    let params = new HttpParams();
    if (activeOnly) params = params.set('active', '1');
    return this.http.get<Account[]>(`${this.api}/config/accounts/`, { params });
  }

  createAccount(payload: {
    name: string;
    account_type?: string;
    order?: number;
    is_active?: boolean;
    is_default_for_expenses?: boolean;
  }) {
    return this.http.post<Account>(`${this.api}/config/accounts/`, payload);
  }

  updateAccount(id: string, payload: Partial<Account>) {
    return this.http.patch<Account>(`${this.api}/config/accounts/${id}/`, payload);
  }

  // ---- Budget planning ----

  incomeStreams(): Observable<IncomeStreamList> {
    return this.http.get<IncomeStreamList>(`${this.api}/income-streams/`);
  }

  createIncomeStream(payload: Partial<IncomeStream>) {
    return this.http.post<IncomeStream>(`${this.api}/income-streams/`, payload);
  }

  updateIncomeStream(id: string, payload: Partial<IncomeStream>) {
    return this.http.patch<IncomeStream>(`${this.api}/income-streams/${id}/`, payload);
  }

  deleteIncomeStream(id: string) {
    return this.http.delete<void>(`${this.api}/income-streams/${id}/`);
  }

  planBuckets(): Observable<PlanBucketRow[]> {
    return this.http.get<PlanBucketRow[]>(`${this.api}/plans/buckets/`);
  }

  savePlanBuckets(buckets: Record<string, PlanBucket>): Observable<PlanBucketRow[]> {
    return this.http.put<PlanBucketRow[]>(`${this.api}/plans/buckets/`, { buckets });
  }

  previewPlans(year: number, month: number): Observable<PlanPreview> {
    return this.http.post<PlanPreview>(`${this.api}/plans/preview/`, { year, month });
  }

  plans(year: number, month: number): Observable<BudgetPlan[]> {
    const params = new HttpParams().set('year', year).set('month', month);
    return this.http.get<BudgetPlan[]>(`${this.api}/plans/`, { params });
  }

  plan(id: string): Observable<BudgetPlan> {
    return this.http.get<BudgetPlan>(`${this.api}/plans/${id}/`);
  }

  createPlan(year: number, month: number, plan_type: PlanType): Observable<BudgetPlan> {
    return this.http.post<BudgetPlan>(`${this.api}/plans/`, { year, month, plan_type });
  }

  updatePlanAmounts(id: string, amounts: Record<string, string>): Observable<BudgetPlan> {
    return this.http.patch<BudgetPlan>(`${this.api}/plans/${id}/`, { amounts });
  }

  acceptPlan(id: string): Observable<BudgetPlan> {
    return this.http.post<BudgetPlan>(`${this.api}/plans/${id}/accept/`, {});
  }

  dismissPlan(id: string): Observable<BudgetPlan> {
    return this.http.post<BudgetPlan>(`${this.api}/plans/${id}/dismiss/`, {});
  }

  // Notifications live at /api/v1/notifications (not under /budgeting).
  notifications(unreadOnly = false): Observable<AppNotification[]> {
    const params = unreadOnly ? new HttpParams().set('unread', '1') : undefined;
    return this.http.get<AppNotification[]>(`${environment.apiUrl}/notifications/`, { params });
  }

  notificationCount(): Observable<{ unread: number }> {
    return this.http.get<{ unread: number }>(`${environment.apiUrl}/notifications/count/`);
  }

  markNotificationRead(id: string) {
    return this.http.post<AppNotification>(`${environment.apiUrl}/notifications/${id}/read/`, {});
  }

  markAllNotificationsRead() {
    return this.http.post<{ marked: number }>(`${environment.apiUrl}/notifications/read-all/`, {});
  }

  deleteAccount(id: string) {
    return this.http.delete(`${this.api}/config/accounts/${id}/`);
  }

  /** @deprecated use accounts() */
  incomeSources(activeOnly = false): Observable<IncomeSource[]> {
    return this.accounts(activeOnly);
  }

  /** @deprecated use createAccount() */
  createIncomeSource(payload: { name: string; order?: number; is_active?: boolean; account_type?: string }) {
    return this.createAccount(payload);
  }

  /** @deprecated use updateAccount() */
  updateIncomeSource(id: string, payload: Partial<IncomeSource>) {
    return this.updateAccount(id, payload);
  }

  /** @deprecated use deleteAccount() */
  deleteIncomeSource(id: string) {
    return this.deleteAccount(id);
  }
}
