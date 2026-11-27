import { Component } from '@angular/core';
import { amountsHidden, toggleAmountsHidden } from '../privacy';

/** The eye in the top bar: hides / shows every money amount (remembered on this device). */
@Component({
  selector: 'app-privacy-toggle',
  standalone: true,
  template: `
    <button
      type="button"
      class="eye"
      [class.on]="hidden()"
      [attr.aria-pressed]="hidden()"
      [attr.aria-label]="hidden() ? 'Show amounts' : 'Hide amounts'"
      [title]="hidden() ? 'Show amounts' : 'Hide amounts'"
      (click)="toggle()"
    >
      @if (hidden()) {
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M10.6 5.1A9.9 9.9 0 0 1 12 5c5.5 0 9.5 4.6 10.5 7-.4 1-1.3 2.4-2.6 3.7" />
          <path d="M6.6 6.6C4.1 8 2.3 10.4 1.5 12c1 2.4 5 7 10.5 7 1.9 0 3.6-.5 5.1-1.4" />
          <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
          <path d="M3 3l18 18" />
        </svg>
      } @else {
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M1.5 12C2.5 9.6 6.5 5 12 5s9.5 4.6 10.5 7c-1 2.4-5 7-10.5 7S2.5 14.4 1.5 12z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      }
    </button>
  `,
  styles: `
    :host {
      display: inline-flex;
    }

    .eye {
      display: grid;
      place-items: center;
      width: 2.4rem;
      height: 2.4rem;
      border: 1px solid rgba(255, 255, 255, 0.25);
      border-radius: 0.5rem;
      background: transparent;
      color: #f4f7f6;
      cursor: pointer;

      svg {
        width: 1.25rem;
        height: 1.25rem;
        fill: none;
        stroke: currentColor;
        stroke-width: 1.8;
        stroke-linecap: round;
        stroke-linejoin: round;
      }

      // Hidden mode stands out a little, so it is not forgotten.
      &.on {
        background: rgba(255, 255, 255, 0.16);
        border-color: rgba(255, 255, 255, 0.5);
      }

      &:hover {
        background: rgba(255, 255, 255, 0.12);
      }

      &:focus-visible {
        outline: 2px solid #c45c26;
        outline-offset: 2px;
      }
    }
  `,
})
export class PrivacyToggleComponent {
  readonly hidden = amountsHidden;

  toggle(): void {
    toggleAmountsHidden();
  }
}
