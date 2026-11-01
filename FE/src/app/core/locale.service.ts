import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { catchError, tap } from 'rxjs/operators';
import { environment } from '../../environments/environment';
import { MetaData, User, UserPreferences } from './models';

const PREFS_KEY = 'ft_locale_prefs';

export const FALLBACK_CURRENCIES = [
  { code: 'USD', label: 'US Dollar' },
  { code: 'LBP', label: 'Lebanese Lira' },
  { code: 'SAR', label: 'Saudi Riyal' },
];

@Injectable({ providedIn: 'root' })
export class LocaleService {
  private http = inject(HttpClient);
  private readonly api = environment.apiUrl;

  readonly preferences = signal<UserPreferences>(this.readCached());
  readonly currencies = signal(FALLBACK_CURRENCIES);

  defaultCurrency(): string {
    return this.preferences().default_currency || 'USD';
  }

  /** Default / report currency for dashboard and CSV exports. */
  reportCurrency(): string {
    return this.defaultCurrency();
  }

  setReportCurrency(code: string): Observable<UserPreferences & { id?: number }> {
    return this.savePreferences({ default_currency: code });
  }

  detectTimezone(): string {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || '';
    } catch {
      return '';
    }
  }

  detectLocale(): string {
    return navigator.language || '';
  }

  /** Today's date (YYYY-MM-DD) in the user's timezone when known. */
  todayIso(): string {
    const tz = this.preferences().timezone || this.detectTimezone();
    try {
      if (tz) {
        const parts = new Intl.DateTimeFormat('en-CA', {
          timeZone: tz,
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
        }).formatToParts(new Date());
        const y = parts.find((p) => p.type === 'year')?.value;
        const m = parts.find((p) => p.type === 'month')?.value;
        const d = parts.find((p) => p.type === 'day')?.value;
        if (y && m && d) return `${y}-${m}-${d}`;
      }
    } catch {
      /* fall through */
    }
    return new Date().toISOString().slice(0, 10);
  }

  /** Current HH:mm in the user's timezone when known. */
  currentTime(): string {
    const tz = this.preferences().timezone || this.detectTimezone();
    try {
      if (tz) {
        return new Intl.DateTimeFormat('en-GB', {
          timeZone: tz,
          hour: '2-digit',
          minute: '2-digit',
          hour12: false,
        }).format(new Date());
      }
    } catch {
      /* fall through */
    }
    const d = new Date();
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  }

  loadMeta(): Observable<MetaData> {
    const tz = this.detectTimezone();
    const locale = this.detectLocale();
    return this.http
      .get<MetaData>(`${this.api}/meta/`, {
        params: { tz, locale },
      })
      .pipe(
        tap((meta) => {
          if (meta.currencies?.length) {
            this.currencies.set(meta.currencies);
          }
          if (meta.suggested) {
            this.applySuggested(meta.suggested, false);
          }
        }),
        catchError(() => {
          this.applySuggested(this.detectLocalDefaults(), false);
          return of({
            currencies: FALLBACK_CURRENCIES,
            consumption_types: [],
            countries: [],
            suggested: this.preferences(),
          });
        })
      );
  }

  /** Sync preferences from /auth/me/ (call after login). */
  syncFromServer(): Observable<UserPreferences> {
    const tz = this.detectTimezone();
    const locale = this.detectLocale();
    return this.http
      .get<UserPreferences & { id?: number }>(`${this.api}/auth/me/`, {
        params: { tz, locale },
      })
      .pipe(
        tap((user) => {
          this.applyFromUser(user);
        }),
        catchError(() => of(this.preferences()))
      );
  }

  savePreferences(
    patch: Partial<
      UserPreferences &
        Pick<User, 'first_name' | 'last_name' | 'email' | 'notify_plan_updates' | 'savings_target_pct'>
    >,
  ): Observable<UserPreferences & { id?: number }> {
    return this.http.patch<UserPreferences & { id?: number }>(`${this.api}/auth/me/`, patch).pipe(
      tap((user) => this.applyFromUser(user)),
    );
  }

  /** Apply server-side profile locale fields (after login). */
  applyFromUser(user: {
    timezone?: string;
    country?: string;
    default_currency?: string;
  }): void {
    this.setPreferences({
      timezone: user.timezone || this.detectTimezone(),
      country: user.country || '',
      default_currency: user.default_currency || this.defaultCurrency(),
    });
  }

  private detectLocalDefaults(): UserPreferences {
    const tz = this.detectTimezone();
    const locale = this.detectLocale();
    let country = '';
    let default_currency = 'USD';
    if (tz === 'Asia/Beirut') {
      country = 'LB';
      default_currency = 'LBP';
    } else if (tz === 'Asia/Riyadh' || tz === 'Asia/Dubai') {
      country = 'SA';
      default_currency = 'SAR';
    } else {
      const region = locale.split('-')[1]?.toUpperCase();
      if (region === 'LB') {
        country = 'LB';
        default_currency = 'LBP';
      } else if (region === 'SA') {
        country = 'SA';
        default_currency = 'SAR';
      }
    }
    return { timezone: tz, country, default_currency };
  }

  private applySuggested(suggested: Partial<UserPreferences>, overwrite: boolean): void {
    const current = this.preferences();
    const next: UserPreferences = {
      timezone: overwrite || !current.timezone ? suggested.timezone || current.timezone : current.timezone,
      country: overwrite || !current.country ? suggested.country || current.country : current.country,
      default_currency:
        overwrite || !current.default_currency || current.default_currency === 'USD'
          ? suggested.default_currency || current.default_currency
          : current.default_currency,
    };
    this.setPreferences(next);
  }

  private setPreferences(prefs: UserPreferences): void {
    this.preferences.set(prefs);
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  }

  private readCached(): UserPreferences {
    const raw = localStorage.getItem(PREFS_KEY);
    if (raw) {
      try {
        return JSON.parse(raw) as UserPreferences;
      } catch {
        /* ignore */
      }
    }
    return this.detectLocalDefaults();
  }
}
