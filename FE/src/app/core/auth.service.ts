import { Injectable, signal, computed, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { finalize, shareReplay, tap } from 'rxjs/operators';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { AuthResponse, AuthTokens, RegisterResponse, User } from './models';
import { LocaleService } from './locale.service';

const ACCESS_KEY = 'ft_access';
const REFRESH_KEY = 'ft_refresh';
const USER_KEY = 'ft_user';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly api = environment.apiUrl;
  private readonly locale = inject(LocaleService);
  private readonly userSignal = signal<User | null>(this.readUser());

  readonly user = this.userSignal.asReadonly();
  readonly isAuthenticated = computed(() => !!this.getAccessToken());

  constructor(private http: HttpClient, private router: Router) {}

  login(username: string, password: string): Observable<AuthTokens> {
    return this.http
      .post<AuthTokens>(`${this.api}/auth/login/`, { username, password })
      .pipe(
        tap((tokens) => {
          this.storeTokens(tokens);
          this.loadMe().subscribe();
        })
      );
  }

  register(payload: {
    username: string;
    email: string;
    first_name: string;
    last_name: string;
    password: string;
    password_confirm: string;
  }): Observable<RegisterResponse> {
    return this.http.post<RegisterResponse>(`${this.api}/auth/register/`, payload).pipe(
      tap((res) => {
        if (res.access) {
          this.storeTokens(res);
          if (res.user) {
            this.setUser(res.user);
          } else {
            this.loadMe().subscribe();
          }
        }
      })
    );
  }

  verifyEmail(uid: string, token: string): Observable<{ detail: string; email_verified?: boolean }> {
    return this.http.post<{ detail: string; email_verified?: boolean }>(
      `${this.api}/auth/email-verify/confirm/`,
      { uid, token }
    );
  }

  resendVerificationEmail(email?: string): Observable<{ detail: string }> {
    return this.http.post<{ detail: string }>(`${this.api}/auth/email-verify/resend/`, { email: email || '' });
  }

  loadMe(): Observable<User> {
    const tz = this.locale.detectTimezone();
    const locale = this.locale.detectLocale();
    return this.http
      .get<User>(`${this.api}/auth/me/`, { params: { tz, locale } })
      .pipe(
        tap((u) => {
          this.setUser(u);
          this.locale.applyFromUser(u);
        })
      );
  }

  /** In-flight token refresh, shared by every request that got a 401 at the same time. */
  private refreshing$: Observable<AuthTokens> | null = null;

  refresh(): Observable<AuthTokens> {
    // Refresh tokens are single-use (rotated, the old one is blacklisted): if several requests
    // expire together they must wait for one refresh instead of each spending the same token.
    if (!this.refreshing$) {
      const refresh = this.getRefreshToken();
      this.refreshing$ = this.http
        .post<AuthTokens>(`${this.api}/auth/token/refresh/`, { refresh })
        .pipe(
          tap((tokens) => this.storeTokens({ access: tokens.access, refresh: tokens.refresh || refresh || undefined })),
          finalize(() => (this.refreshing$ = null)),
          shareReplay(1)
        );
    }
    return this.refreshing$;
  }

  /**
   * The session can no longer be renewed (refresh token expired or revoked): clear it and open
   * the sign-in page, which brings the user back to `returnUrl` after signing in.
   */
  private redirectingToLogin = false;

  sessionExpired(): void {
    // Several requests fail together: only the first one redirects (and keeps the message).
    if (this.redirectingToLogin) return;
    const hadSession = !!this.getAccessToken() || !!this.getRefreshToken();
    this.clearSession();
    const current = this.router.url;
    if (current.startsWith('/login')) return;
    this.redirectingToLogin = true;
    this.router
      .navigate(['/login'], { queryParams: { returnUrl: current, expired: hadSession ? '1' : null } })
      .finally(() => (this.redirectingToLogin = false));
  }

  logout(): void {
    const refresh = this.getRefreshToken();
    if (refresh) {
      // Revoke server-side; sign-out proceeds locally even if this fails.
      this.http.post(`${this.api}/auth/logout/`, { refresh }).subscribe({ error: () => undefined });
    }
    this.clearSession();
    this.router.navigate(['/login']);
  }

  /** Clear stored auth without navigating (e.g. before email verification). */
  clearSession(): void {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(USER_KEY);
    this.userSignal.set(null);
  }

  requestPasswordReset(identifier: string): Observable<{ detail: string }> {
    return this.http.post<{ detail: string }>(`${this.api}/auth/password-reset/`, { identifier });
  }

  confirmPasswordReset(payload: {
    uid: string;
    token: string;
    password: string;
    password_confirm: string;
  }): Observable<{ detail: string }> {
    return this.http.post<{ detail: string }>(`${this.api}/auth/password-reset/confirm/`, payload);
  }

  getAccessToken(): string | null {
    return localStorage.getItem(ACCESS_KEY);
  }

  getRefreshToken(): string | null {
    return localStorage.getItem(REFRESH_KEY);
  }

  private storeTokens(tokens: Partial<AuthTokens>): void {
    if (tokens.access) {
      localStorage.setItem(ACCESS_KEY, tokens.access);
    }
    if (tokens.refresh) {
      localStorage.setItem(REFRESH_KEY, tokens.refresh);
    }
  }

  private setUser(user: User): void {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
    this.userSignal.set(user);
  }

  private readUser(): User | null {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as User;
    } catch {
      return null;
    }
  }
}
