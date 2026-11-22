import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import {
  AdminOverview,
  AdminUserAction,
  AdminUserDetail,
  AdminUserEditable,
  AdminUserFilters,
  AdminUserPage,
  AuditLogRow,
  Campaign,
  CampaignAudience,
  CampaignInput,
  CampaignStatus,
  MessageContent,
  MessageDelivery,
  MessagePreview,
  MessageTemplate,
  MessagingMeta,
  SendMessageResult,
  UserMessages,
  Paged,
  SupportSettings,
  SupportTicket,
  UserRef,
  AdminDashboard,
  OverviewDays,
} from './models';

function params(values: Record<string, string | number | null | undefined>): HttpParams {
  let p = new HttpParams();
  for (const [k, v] of Object.entries(values)) {
    if (v !== null && v !== undefined && v !== '') p = p.set(k, v);
  }
  return p;
}

/** Staff-only admin & customer-support API. */
@Injectable({ providedIn: 'root' })
export class AdminService {
  private readonly api = `${environment.apiUrl}/admin`;

  constructor(private http: HttpClient) {}

  overview(): Observable<AdminOverview> {
    return this.http.get<AdminOverview>(`${this.api}/overview/`);
  }

  /** The overview page: the counts plus the sections for the last `days` days. */
  dashboard(days: OverviewDays): Observable<AdminDashboard> {
    return this.http.get<AdminDashboard>(`${this.api}/overview/`, { params: { days } });
  }

  users(filters: AdminUserFilters): Observable<AdminUserPage> {
    return this.http.get<AdminUserPage>(`${this.api}/users/`, { params: params({ ...filters }) });
  }

  user(id: number | string): Observable<AdminUserDetail> {
    return this.http.get<AdminUserDetail>(`${this.api}/users/${id}/`);
  }

  updateUser(id: number | string, patch: Partial<AdminUserEditable>): Observable<AdminUserDetail> {
    return this.http.patch<AdminUserDetail>(`${this.api}/users/${id}/`, patch);
  }

  /** notify / reason: deactivate and reactivate can tell the user (account notice template). */
  userAction(
    id: number | string,
    action: AdminUserAction,
    body: { notify?: boolean; reason?: string } = {}
  ): Observable<{ ok: boolean; email_sent?: boolean; notified?: boolean }> {
    return this.http.post<{ ok: boolean; email_sent?: boolean; notified?: boolean }>(
      `${this.api}/users/${id}/${action}/`,
      body
    );
  }

  setRole(id: number | string, isStaff: boolean): Observable<{ ok: boolean }> {
    return this.http.post<{ ok: boolean }>(`${this.api}/users/${id}/role/`, { is_staff: isStaff });
  }

  staff(): Observable<UserRef[]> {
    return this.http.get<UserRef[]>(`${this.api}/staff/`);
  }

  tickets(filters: { view?: 'mine' | 'pool' | 'all'; status?: string; q?: string; page?: number }): Observable<Paged<SupportTicket>> {
    return this.http.get<Paged<SupportTicket>>(`${this.api}/tickets/`, { params: params(filters) });
  }

  /** Take an unassigned ticket from the pool. */
  claimTicket(id: number | string): Observable<SupportTicket> {
    return this.http.post<SupportTicket>(`${this.api}/tickets/${id}/claim/`, {});
  }

  /** Tell the user it is fixed; they confirm (closes) or say it is not fixed. */
  resolveTicket(id: number | string, message: string): Observable<SupportTicket> {
    return this.http.post<SupportTicket>(`${this.api}/tickets/${id}/resolve/`, { message });
  }

  supportSettings(): Observable<SupportSettings> {
    return this.http.get<SupportSettings>(`${this.api}/support-settings/`);
  }

  updateSupportSettings(
    payload: Partial<Pick<SupportSettings, 'assignment_mode' | 'reminder_days' | 'auto_close_days' | 'email_admins'>>
  ): Observable<SupportSettings> {
    return this.http.patch<SupportSettings>(`${this.api}/support-settings/`, payload);
  }

  ticket(id: number | string): Observable<SupportTicket> {
    return this.http.get<SupportTicket>(`${this.api}/tickets/${id}/`);
  }

  updateTicket(
    id: number | string,
    payload: Partial<{ priority: string; assigned_to: number | null }>
  ): Observable<SupportTicket> {
    return this.http.patch<SupportTicket>(`${this.api}/tickets/${id}/`, payload);
  }

  replyTicket(id: number | string, body: string): Observable<SupportTicket> {
    return this.http.post<SupportTicket>(`${this.api}/tickets/${id}/reply/`, { body });
  }

  // ---- Notification center ----

  messagingMeta(): Observable<MessagingMeta> {
    return this.http.get<MessagingMeta>(`${this.api}/messaging/`);
  }

  createTemplate(payload: Partial<MessageTemplate>): Observable<MessageTemplate> {
    return this.http.post<MessageTemplate>(`${this.api}/message-templates/`, payload);
  }

  updateTemplate(key: string, payload: Partial<MessageTemplate>): Observable<MessageTemplate> {
    return this.http.patch<MessageTemplate>(`${this.api}/message-templates/${key}/`, payload);
  }

  deleteTemplate(key: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/message-templates/${key}/`);
  }

  userMessages(id: number | string): Observable<UserMessages> {
    return this.http.get<UserMessages>(`${this.api}/users/${id}/messages/`);
  }

  previewUserMessage(
    id: number | string,
    payload: Partial<MessageContent> & { template_key: string; reason?: string }
  ): Observable<MessagePreview> {
    return this.http.post<MessagePreview>(`${this.api}/users/${id}/messages/`, { ...payload, preview: true });
  }

  sendUserMessage(
    id: number | string,
    payload: Partial<MessageContent> & { template_key: string; reason?: string }
  ): Observable<SendMessageResult> {
    return this.http.post<SendMessageResult>(`${this.api}/users/${id}/messages/`, payload);
  }

  campaigns(filters: { status?: CampaignStatus | ''; page?: number } = {}): Observable<Paged<Campaign>> {
    return this.http.get<Paged<Campaign>>(`${this.api}/campaigns/`, { params: params(filters) });
  }

  campaign(id: number | string): Observable<Campaign> {
    return this.http.get<Campaign>(`${this.api}/campaigns/${id}/`);
  }

  createCampaign(payload: CampaignInput): Observable<Campaign> {
    return this.http.post<Campaign>(`${this.api}/campaigns/`, payload);
  }

  updateCampaign(id: number | string, payload: Partial<CampaignInput>): Observable<Campaign> {
    return this.http.patch<Campaign>(`${this.api}/campaigns/${id}/`, payload);
  }

  deleteCampaign(id: number | string): Observable<void> {
    return this.http.delete<void>(`${this.api}/campaigns/${id}/`);
  }

  /** How many active users the audience reaches, plus a few of them. */
  audienceCount(audience: CampaignAudience): Observable<{ count: number; sample: UserRef[] }> {
    return this.http.post<{ count: number; sample: UserRef[] }>(`${this.api}/campaigns/audience/`, { audience });
  }

  /** Send the campaign to yourself only. */
  testCampaign(id: number | string): Observable<SendMessageResult> {
    return this.http.post<SendMessageResult>(`${this.api}/campaigns/${id}/test/`, {});
  }

  /** confirmCount: the audience size the admin confirmed (409 when it changed). */
  sendCampaign(id: number | string, confirmCount: number, scheduledAt?: string | null): Observable<Campaign> {
    return this.http.post<Campaign>(`${this.api}/campaigns/${id}/send/`, {
      confirm_count: confirmCount,
      scheduled_at: scheduledAt || null,
    });
  }

  cancelCampaign(id: number | string): Observable<Campaign> {
    return this.http.post<Campaign>(`${this.api}/campaigns/${id}/cancel/`, {});
  }

  campaignDeliveries(
    id: number | string,
    filters: { status?: string; channel?: string; page?: number } = {}
  ): Observable<Paged<MessageDelivery>> {
    return this.http.get<Paged<MessageDelivery>>(`${this.api}/campaigns/${id}/deliveries/`, { params: params(filters) });
  }

  auditLog(filters: { user?: number | string; actor?: number | string; page?: number }): Observable<Paged<AuditLogRow>> {
    return this.http.get<Paged<AuditLogRow>>(`${this.api}/audit-log/`, { params: params(filters) });
  }
}
