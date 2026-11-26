import { AfterViewInit, Directive, ElementRef, OnDestroy, Renderer2, inject, input } from '@angular/core';
import { AuthService } from '../core/auth.service';

const STORAGE_KEY = 'collapsed_cards';

/** Card ids folded by this user in this browser. */
function loadCollapsed(key: string): Set<string> {
  try {
    const raw = JSON.parse(localStorage.getItem(key) || '[]');
    return new Set(Array.isArray(raw) ? raw.filter((v) => typeof v === 'string') : []);
  } catch {
    return new Set();
  }
}

function saveCollapsed(key: string, ids: Set<string>): void {
  try {
    localStorage.setItem(key, JSON.stringify([...ids]));
  } catch {
    /* storage unavailable: the choice lasts until the page is closed */
  }
}

/**
 * Adds a fold button to a card (a `section` whose first child is a `header`): folded, only the
 * header shows. Works on a card element or on a component whose template is such a card, without
 * changing the component. The choice is remembered per card id and per user in this browser.
 *
 *   <app-account-balances-widget appCollapsibleCard="balances" />
 *   <section class="panel" appCollapsibleCard="year"><header>…</header>…</section>
 */
@Directive({ selector: '[appCollapsibleCard]', standalone: true })
export class CollapsibleCardDirective implements AfterViewInit, OnDestroy {
  /** Stable id used to remember the choice. */
  appCollapsibleCard = input.required<string>();

  private host = inject<ElementRef<HTMLElement>>(ElementRef);
  private renderer = inject(Renderer2);
  private auth = inject(AuthService);
  private observer?: MutationObserver;
  private card: HTMLElement | null = null;
  private button: HTMLButtonElement | null = null;
  private unlisten?: () => void;

  ngAfterViewInit(): void {
    if (!this.attach() && typeof MutationObserver !== 'undefined') {
      // The component may render its card a moment later.
      this.observer = new MutationObserver(() => {
        if (this.attach()) this.observer?.disconnect();
      });
      this.observer.observe(this.host.nativeElement, { childList: true, subtree: true });
    }
  }

  ngOnDestroy(): void {
    this.observer?.disconnect();
    this.unlisten?.();
  }

  private get storageKey(): string {
    const id = this.auth.user()?.id;
    return id ? `${STORAGE_KEY}_${id}` : STORAGE_KEY;
  }

  private findCard(): HTMLElement | null {
    const el = this.host.nativeElement;
    if (el.tagName === 'SECTION' && el.querySelector(':scope > header')) return el;
    const section = el.querySelector<HTMLElement>('section');
    return section?.querySelector(':scope > header') ? section : null;
  }

  private attach(): boolean {
    const card = this.findCard();
    if (!card) return false;
    const header = card.querySelector<HTMLElement>(':scope > header')!;
    this.card = card;
    this.renderer.addClass(card, 'cc-card');
    this.renderer.addClass(header, 'cc-head');

    const button = this.renderer.createElement('button') as HTMLButtonElement;
    button.type = 'button';
    button.className = 'cc-toggle';
    button.innerHTML = '<span class="cc-chev" aria-hidden="true">▾</span>';
    this.renderer.appendChild(card, button);
    this.button = button;
    this.unlisten = this.renderer.listen(button, 'click', () => this.set(!card.classList.contains('cc-collapsed')));

    this.apply(loadCollapsed(this.storageKey).has(this.appCollapsibleCard()));
    return true;
  }

  private set(collapsed: boolean): void {
    const ids = loadCollapsed(this.storageKey);
    if (collapsed) ids.add(this.appCollapsibleCard());
    else ids.delete(this.appCollapsibleCard());
    saveCollapsed(this.storageKey, ids);
    this.apply(collapsed);
  }

  private apply(collapsed: boolean): void {
    if (!this.card || !this.button) return;
    this.card.classList.toggle('cc-collapsed', collapsed);
    // A folded card should not stretch to the height of its neighbours in a grid row.
    this.host.nativeElement.classList.toggle('cc-host-collapsed', collapsed);
    const title = this.card.querySelector(':scope > header h2, :scope > header h3')?.textContent?.trim() || 'card';
    this.button.setAttribute('aria-expanded', String(!collapsed));
    this.button.setAttribute('aria-label', `${collapsed ? 'Expand' : 'Collapse'} ${title}`);
    this.button.title = collapsed ? 'Expand' : 'Collapse';
  }
}
