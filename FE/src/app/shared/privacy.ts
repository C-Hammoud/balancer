import { signal } from '@angular/core';

/**
 * Privacy mode: the eye in the top bar hides every money amount (•••• instead of the number).
 * Remembered on this device. A plain signal (not a service) so formatAmount() can read it;
 * templates track the read, so toggling updates the screen at once.
 */
const STORAGE_KEY = 'ft_hide_amounts';
const HTML_CLASS = 'amounts-hidden';

export const HIDDEN_AMOUNT = '••••';

function readStored(): boolean {
  try {
    return typeof localStorage !== 'undefined' && localStorage.getItem(STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

function applyClass(hidden: boolean): void {
  if (typeof document !== 'undefined') document.documentElement.classList.toggle(HTML_CLASS, hidden);
}

const hiddenState = signal(readStored());
applyClass(hiddenState());

/** True while amounts are hidden. */
export const amountsHidden = hiddenState.asReadonly();

export function setAmountsHidden(hidden: boolean): void {
  hiddenState.set(hidden);
  applyClass(hidden);
  try {
    if (hidden) localStorage.setItem(STORAGE_KEY, '1');
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* private browsing: still works for this visit */
  }
}

export function toggleAmountsHidden(): void {
  setAmountsHidden(!hiddenState());
}

const CURRENCY = '(?:USD|SAR|LBP|EUR|GBP|AED|KWD|QAR|BHD|OMR|JOD|EGP)';
// "1,350.00", "1350.00", "1,500" — or any number next to a currency code ("SAR 120", "45 USD").
const AMOUNT_IN_TEXT = new RegExp(
  [
    `${CURRENCY}\\s?-?\\d[\\d,]*(?:\\.\\d+)?`,
    `-?\\d[\\d,]*(?:\\.\\d+)?(?=\\s?${CURRENCY}\\b)`,
    `-?\\d{1,3}(?:,\\d{3})+(?:\\.\\d+)?(?!\\s?%)`,
    `-?\\d+\\.\\d+(?![\\d.]*\\s?%)`,
  ].join('|'),
  'g',
);

/**
 * Hide the amounts inside a sentence written by the server ("actual 1350.00 SAR, forecast
 * 1500.00 SAR"). Percentages, dates and plain counts stay.
 */
export function hideAmountsInText(text: string): string {
  return text.replace(AMOUNT_IN_TEXT, (m) => {
    const code = m.match(new RegExp(`^${CURRENCY}`));
    return code ? `${code[0]} ${HIDDEN_AMOUNT}` : HIDDEN_AMOUNT;
  });
}
