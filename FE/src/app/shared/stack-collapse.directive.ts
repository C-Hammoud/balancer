import { AfterViewInit, Directive, ElementRef, NgZone, OnDestroy, inject } from '@angular/core';

/** Same width as the stacked-card table layout in styles.scss. */
export const PHONE_QUERY = '(max-width: 640px)';

const INTERACTIVE = 'a, button, input, select, textarea, label, [contenteditable], td[data-summary~="select"]';

/**
 * Phone view of a `.stack-table`: each row card starts collapsed to one compact line and opens on
 * tap (or Enter / Space), showing every field and the row's buttons.
 *
 * Cells marked `data-summary` stay visible when collapsed:
 *   title   main text (one line)          end     right-aligned value (amount)
 *   meta    small second line             select  the row's checkbox
 *   labeled add to meta to show the column name ("Spent 120")
 * Rows without a data-summary cell (empty states, group headings) are left as they are.
 * On wider screens nothing changes.
 */
@Directive({ selector: '[appStackCollapse]', standalone: true })
export class StackCollapseDirective implements AfterViewInit, OnDestroy {
  private host = inject<ElementRef<HTMLElement>>(ElementRef);
  private zone = inject(NgZone);
  private media = typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(PHONE_QUERY) : null;
  private observer?: MutationObserver;
  private frame = 0;

  ngAfterViewInit(): void {
    const root = this.host.nativeElement;
    this.zone.runOutsideAngular(() => {
      root.addEventListener('click', this.onClick);
      root.addEventListener('keydown', this.onKey);
      this.media?.addEventListener?.('change', this.schedule);
      if (typeof MutationObserver !== 'undefined') {
        this.observer = new MutationObserver(this.schedule);
        this.observer.observe(root, { childList: true, subtree: true });
      }
    });
    this.mark();
  }

  ngOnDestroy(): void {
    const root = this.host.nativeElement;
    root.removeEventListener('click', this.onClick);
    root.removeEventListener('keydown', this.onKey);
    this.media?.removeEventListener?.('change', this.schedule);
    this.observer?.disconnect();
    if (this.frame) cancelAnimationFrame(this.frame);
  }

  private get phone(): boolean {
    return !!this.media?.matches;
  }

  private schedule = (): void => {
    if (this.frame) return;
    this.frame = requestAnimationFrame(() => {
      this.frame = 0;
      this.mark();
    });
  };

  /** Tag the rows (new ones appear as data loads) and make the collapsible ones focusable on phones. */
  private mark(): void {
    const rows = this.host.nativeElement.querySelectorAll<HTMLTableRowElement>('tbody tr');
    rows.forEach((tr) => {
      const cells = Array.from(tr.children).filter((c) => c.tagName === 'TD');
      const summary = cells.some((c) => c.hasAttribute('data-summary'));
      tr.classList.toggle('sc-row', summary);
      // Only rows that hide something get the tap-to-open behaviour and the ▾ marker.
      const hidden = cells.filter((c) => !c.hasAttribute('data-summary'));
      const more =
        summary && hidden.some((c) => (c.textContent ?? '').trim() !== '' || !!c.querySelector('button, a, input, select'));
      tr.classList.toggle('sc-more', more);
      if (more && this.phone) {
        tr.tabIndex = 0;
        tr.setAttribute('aria-expanded', String(tr.classList.contains('sc-open')));
      } else {
        tr.removeAttribute('tabindex');
        tr.removeAttribute('aria-expanded');
      }
    });
  }

  private toggle(tr: HTMLElement): void {
    const open = tr.classList.toggle('sc-open');
    tr.setAttribute('aria-expanded', String(open));
  }

  private onClick = (event: Event): void => {
    if (!this.phone) return;
    const target = event.target as Element | null;
    if (!target) return;
    // The checkbox cell is a larger tap area for its (small) checkbox.
    const selectCell = target.closest('td[data-summary~="select"]');
    if (selectCell && !target.closest('input, label')) {
      selectCell.querySelector<HTMLInputElement>('input[type="checkbox"]:not(:disabled)')?.click();
      return;
    }
    if (target.closest(INTERACTIVE)) return;
    const tr = target.closest<HTMLElement>('tr.sc-more');
    if (!tr || !this.host.nativeElement.contains(tr)) return;
    // Selecting text to copy it is not a tap.
    if (window.getSelection?.()?.toString()) return;
    this.toggle(tr);
  };

  private onKey = (event: KeyboardEvent): void => {
    if (!this.phone || (event.key !== 'Enter' && event.key !== ' ')) return;
    const tr = event.target as HTMLElement;
    if (!tr?.classList?.contains('sc-more')) return;
    event.preventDefault();
    this.toggle(tr);
  };
}
