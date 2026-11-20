import { Injectable, computed, signal } from '@angular/core';

/** Chrome / Edge / Android event offering to install the app (not in the DOM typings). */
interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

type PwaWindow = Window & { navigator: Navigator & { standalone?: boolean } };

/** iPhone / iPad Safari, including iPadOS that reports itself as a Mac with touch. */
export function isIosDevice(nav: Navigator): boolean {
  const ua = nav.userAgent || '';
  return /iphone|ipad|ipod/i.test(ua) || (/macintosh/i.test(ua) && (nav.maxTouchPoints || 0) > 1);
}

/**
 * "Install app": keeps the browser's install offer (Android, desktop Chrome and Edge) so a button
 * can show it later, and tells iPhone users how to add the app to the home screen (Safari has no
 * install prompt). Created at start-up (app.config.ts) so the early event is not missed.
 */
@Injectable({ providedIn: 'root' })
export class PwaInstallService {
  private deferred: BeforeInstallPromptEvent | null = null;
  private readonly promptAvailable = signal(false);
  private readonly isInstalled = signal(false);
  private readonly ios = signal(false);

  /** The browser can show its install prompt. */
  readonly canInstall = computed(() => this.promptAvailable() && !this.isInstalled());
  /** iPhone/iPad not yet installed: show "Share → Add to Home Screen". */
  readonly iosInstructions = computed(() => this.ios() && !this.isInstalled());
  readonly installed = this.isInstalled.asReadonly();

  constructor() {
    this.setup(typeof window === 'undefined' ? null : window);
  }

  /** Separate from the constructor so tests can pass a fake window. */
  setup(win: PwaWindow | null): void {
    if (!win) return;
    const standalone =
      win.matchMedia?.('(display-mode: standalone)').matches === true || win.navigator.standalone === true;
    this.isInstalled.set(standalone);
    win.addEventListener('beforeinstallprompt', (event: Event) => {
      event.preventDefault(); // keep it for our own button instead of the browser's mini-bar
      this.deferred = event as BeforeInstallPromptEvent;
      this.promptAvailable.set(true);
    });
    win.addEventListener('appinstalled', () => {
      this.deferred = null;
      this.promptAvailable.set(false);
      this.isInstalled.set(true);
    });
    this.ios.set(isIosDevice(win.navigator));
  }

  /** Show the browser's install prompt; resolves true when the user accepts. */
  async install(): Promise<boolean> {
    const event = this.deferred;
    if (!event) return false;
    await event.prompt();
    const choice = await event.userChoice;
    // The event can only be used once.
    this.deferred = null;
    this.promptAvailable.set(false);
    return choice.outcome === 'accepted';
  }
}
