import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { environment } from '../../environments/environment';
import { AuthService } from './auth.service';

/** Reads the service worker keeps offline copies of (ngsw-config.json "api-read"). */
const OFFLINE_CACHED = /\/api\/v1\/(budgeting|risk|notifications)\//;

/** Query parameter that ties an offline copy to its user; the API ignores it. */
export const OFFLINE_USER_PARAM = '_u';

/**
 * The service worker stores responses by URL and ignores the Authorization header. Add the
 * signed-in user's id to the cached reads so one user's saved data is never shown to someone
 * else who signs in on the same device while offline. Only while a service worker controls the
 * page: without one nothing is cached and the URLs stay as they are.
 */
export const offlineCacheKeyInterceptor: HttpInterceptorFn = (req, next) => {
  if (req.method !== 'GET' || !OFFLINE_CACHED.test(req.url) || !req.url.startsWith(environment.apiUrl)) {
    return next(req);
  }
  if (typeof navigator === 'undefined' || !navigator.serviceWorker?.controller) {
    return next(req);
  }
  const userId = inject(AuthService).user()?.id;
  if (!userId) return next(req);
  return next(req.clone({ setParams: { [OFFLINE_USER_PARAM]: String(userId) } }));
};
