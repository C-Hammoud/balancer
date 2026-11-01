import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';
import { AuthService } from './auth.service';

export const authGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (auth.getAccessToken()) {
    return true;
  }
  // Keep where the user was going (e.g. a link in an email) so sign-in brings them back there.
  return router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });
};

export const guestGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (!auth.getAccessToken()) {
    return true;
  }
  return router.createUrlTree(['/dashboard']);
};

/**
 * Admin area: support staff and superusers only (the API enforces the same rule).
 * Asks the server, so a role granted or removed since sign-in applies right away.
 */
export const staffGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  const dashboard = router.createUrlTree(['/dashboard']);
  return auth.loadMe().pipe(
    map((user) => (user.is_staff || user.is_superuser ? true : dashboard)),
    catchError(() => of(dashboard))
  );
};
