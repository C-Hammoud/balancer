import { TestBed } from '@angular/core/testing';
import { PwaInstallService, isIosDevice } from './pwa-install.service';

/** A window stand-in: dispatches events, answers matchMedia, carries a navigator. */
function fakeWindow(opts: { userAgent?: string; maxTouchPoints?: number; standalone?: boolean; displayStandalone?: boolean }) {
  const target = new EventTarget();
  return Object.assign(target, {
    navigator: {
      userAgent: opts.userAgent ?? 'Mozilla/5.0 (Windows NT 10.0) Chrome/130',
      maxTouchPoints: opts.maxTouchPoints ?? 0,
      standalone: opts.standalone,
    },
    matchMedia: () => ({ matches: !!opts.displayStandalone }),
  }) as unknown as Window & { navigator: Navigator & { standalone?: boolean } };
}

function installPrompt(outcome: 'accepted' | 'dismissed') {
  const event = new Event('beforeinstallprompt', { cancelable: true }) as Event & {
    prompt: jasmine.Spy;
    userChoice: Promise<{ outcome: string }>;
  };
  event.prompt = jasmine.createSpy('prompt').and.resolveTo();
  event.userChoice = Promise.resolve({ outcome });
  return event;
}

describe('PwaInstallService', () => {
  let service: PwaInstallService;

  beforeEach(() => {
    service = TestBed.inject(PwaInstallService);
  });

  it('offers to install once the browser sends its install prompt', async () => {
    const win = fakeWindow({});
    service.setup(win);
    expect(service.canInstall()).toBeFalse();

    const event = installPrompt('accepted');
    win.dispatchEvent(event);
    expect(event.defaultPrevented).toBeTrue();
    expect(service.canInstall()).toBeTrue();

    expect(await service.install()).toBeTrue();
    expect(event.prompt).toHaveBeenCalled();
    expect(service.canInstall()).toBeFalse(); // the prompt can only be used once
  });

  it('hides everything once installed', () => {
    const win = fakeWindow({});
    service.setup(win);
    win.dispatchEvent(installPrompt('accepted'));
    win.dispatchEvent(new Event('appinstalled'));
    expect(service.installed()).toBeTrue();
    expect(service.canInstall()).toBeFalse();
  });

  it('shows iPhone instructions only when not opened from the home screen', () => {
    const iphone = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Safari/604.1';
    service.setup(fakeWindow({ userAgent: iphone }));
    expect(service.iosInstructions()).toBeTrue();

    service.setup(fakeWindow({ userAgent: iphone, standalone: true }));
    expect(service.installed()).toBeTrue();
    expect(service.iosInstructions()).toBeFalse();
  });

  it('treats a desktop browser in standalone display as installed', () => {
    service.setup(fakeWindow({ displayStandalone: true }));
    expect(service.installed()).toBeTrue();
  });

  it('recognises iPadOS, which reports itself as a Mac with touch', () => {
    const mac = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15';
    expect(isIosDevice({ userAgent: mac, maxTouchPoints: 5 } as Navigator)).toBeTrue();
    expect(isIosDevice({ userAgent: mac, maxTouchPoints: 0 } as Navigator)).toBeFalse();
  });
});
