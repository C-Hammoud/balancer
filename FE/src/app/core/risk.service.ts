import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import {
  AccountBalancesResponse,
  PlannedItem,
  PlannedItemList,
  PlannedItemPayload,
  RiskHistoryPoint,
  RiskReport,
  RiskSettings,
  RiskSettingsPatch,
} from './models';

/** Debt & liquidity risk, planned items and server-side account balances. */
@Injectable({ providedIn: 'root' })
export class RiskService {
  private readonly api = environment.apiUrl;

  /** refresh=true also re-evaluates the risk alerts right away. */
  report(refresh = false): Observable<RiskReport> {
    const params = refresh ? new HttpParams().set('refresh', 1) : undefined;
    return this.http.get<RiskReport>(`${this.api}/risk/`, { params });
  }

  history(days = 90): Observable<{ days: number; points: RiskHistoryPoint[] }> {
    const params = new HttpParams().set('days', days);
    return this.http.get<{ days: number; points: RiskHistoryPoint[] }>(`${this.api}/risk/history/`, { params });
  }

  settings(): Observable<RiskSettings> {
    return this.http.get<RiskSettings>(`${this.api}/risk/settings/`);
  }

  updateSettings(payload: RiskSettingsPatch): Observable<RiskSettings> {
    return this.http.patch<RiskSettings>(`${this.api}/risk/settings/`, payload);
  }

  accountBalances(reportCurrency?: string): Observable<AccountBalancesResponse> {
    const params = reportCurrency ? new HttpParams().set('report_currency', reportCurrency) : undefined;
    return this.http.get<AccountBalancesResponse>(`${this.api}/budgeting/config/accounts/balances/`, { params });
  }

  plannedItems(): Observable<PlannedItemList> {
    return this.http.get<PlannedItemList>(`${this.api}/budgeting/planned-items/`);
  }

  createPlannedItem(payload: PlannedItemPayload): Observable<PlannedItem> {
    return this.http.post<PlannedItem>(`${this.api}/budgeting/planned-items/`, payload);
  }

  updatePlannedItem(id: string, payload: PlannedItemPayload): Observable<PlannedItem> {
    return this.http.patch<PlannedItem>(`${this.api}/budgeting/planned-items/${id}/`, payload);
  }

  deletePlannedItem(id: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/budgeting/planned-items/${id}/`);
  }

  constructor(private http: HttpClient) {}
}
