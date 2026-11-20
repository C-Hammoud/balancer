import {
  ApplicationConfig,
  inject,
  isDevMode,
  provideAppInitializer,
  provideZoneChangeDetection,
} from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideServiceWorker } from '@angular/service-worker';

import { routes } from './app.routes';
import { authInterceptor } from './core/auth.interceptor';
import { dataChangedInterceptor } from './core/data-changed.interceptor';
import { offlineCacheKeyInterceptor } from './core/offline-cache.interceptor';
import { PwaInstallService } from './core/pwa-install.service';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes),
    provideHttpClient(withInterceptors([offlineCacheKeyInterceptor, authInterceptor, dataChangedInterceptor])),
    // Installable app + offline (ngsw-config.json). Production builds only; it needs HTTPS or localhost.
    provideServiceWorker('ngsw-worker.js', {
      enabled: !isDevMode(),
      registrationStrategy: 'registerWhenStable:30000',
    }),
    // Listen for the browser's install offer from the start, before any page asks for it.
    provideAppInitializer(() => {
      inject(PwaInstallService);
    }),
  ],
};
