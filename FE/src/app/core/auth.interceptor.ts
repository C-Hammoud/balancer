import { HttpInterceptorFn, HttpErrorResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, switchMap, throwError } from 'rxjs';
import { AuthService } from './auth.service';

const PUBLIC_AUTH_PATHS = [
  '/auth/login',
  '/auth/register',
  '/auth/token/refresh',
  '/auth/email-verify/',
  '/auth/password-reset',
];

function isPublicAuthRequest(url: string): boolean {
  return PUBLIC_AUTH_PATHS.some((path) => url.includes(path));
}

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const skipAuth = isPublicAuthRequest(req.url);
  const token = skipAuth ? null : auth.getAccessToken();
  const authReq = token
    ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
    : req;

  return next(authReq).pipe(
    catchError((err: HttpErrorResponse) => {
      if (
        err.status !== 401 ||
        skipAuth ||
        req.url.includes('/auth/login') ||
        req.url.includes('/auth/token/refresh')
      ) {
        return throwError(() => err);
      }
      const refresh = auth.getRefreshToken();
      if (!refresh) {
        auth.sessionExpired();
        return throwError(() => err);
      }
      let refreshed = false;
      return auth.refresh().pipe(
        switchMap((tokens) => {
          refreshed = true;
          const retry = req.clone({
            setHeaders: { Authorization: `Bearer ${tokens.access}` },
          });
          return next(retry);
        }),
        catchError((retryErr: HttpErrorResponse) => {
          // Refresh rejected (token expired/revoked), or the retried call is still refused:
          // the session is over, so ask the user to sign in again.
          // A network error or server outage (status 0 / 5xx) is not a lost session.
          const rejected = retryErr.status === 401 || (!refreshed && retryErr.status === 400);
          if (rejected) {
            auth.sessionExpired();
          }
          return throwError(() => retryErr);
        })
      );
    })
  );
};
