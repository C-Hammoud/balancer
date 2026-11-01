import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { SupportTicket, TicketCategory } from './models';

/** Help & support for the signed-in user: report a problem, follow the conversation. */
@Injectable({ providedIn: 'root' })
export class SupportService {
  private readonly api = `${environment.apiUrl}/support/tickets`;

  constructor(private http: HttpClient) {}

  tickets(): Observable<SupportTicket[]> {
    return this.http.get<SupportTicket[]>(`${this.api}/`);
  }

  ticket(id: number | string): Observable<SupportTicket> {
    return this.http.get<SupportTicket>(`${this.api}/${id}/`);
  }

  create(payload: { subject: string; category: TicketCategory; message: string }): Observable<SupportTicket> {
    return this.http.post<SupportTicket>(`${this.api}/`, payload);
  }

  reply(id: number | string, body: string): Observable<SupportTicket> {
    return this.http.post<SupportTicket>(`${this.api}/${id}/reply/`, { body });
  }

  /** Answer "is it fixed?": true closes the request, false sends it back to support. */
  confirm(id: number | string, fixed: boolean, comment = ''): Observable<SupportTicket> {
    return this.http.post<SupportTicket>(`${this.api}/${id}/confirm/`, { fixed, comment });
  }
}
