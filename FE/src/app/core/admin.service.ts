import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import {
  AdminOverview,
  AdminUserAction,
  AdminUserDetail,
  AdminUserRow,
  AuditLogRow,
  Paged,
  SupportSettings,
  SupportTicket,
  UserRef,
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

  users(filters: { q?: string; status?: string; flag?: string; page?: number }): Observable<Paged<AdminUserRow>> {
    return this.http.get<Paged<AdminUserRow>>(`${this.api}/users/`, { params: params(filters) });
  }

  user(id: number | string): Observable<AdminUserDetail> {
    return this.http.get<AdminUserDetail>(`${this.api}/users/${id}/`);
  }

  userAction(id: number | string, action: AdminUserAction): Observable<{ ok: boolean; email_sent?: boolean }> {
    return this.http.post<{ ok: boolean; email_sent?: boolean }>(`${this.api}/users/${id}/${action}/`, {});
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

  auditLog(filters: { user?: number | string; actor?: number | string; page?: number }): Observable<Paged<AuditLogRow>> {
    return this.http.get<Paged<AuditLogRow>>(`${this.api}/audit-log/`, { params: params(filters) });
  }
}
