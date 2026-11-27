import { TestBed } from '@angular/core/testing';
import { AmountPipe, PrivateTextPipe, formatAmount } from './amount.pipe';
import { HIDDEN_AMOUNT, amountsHidden, hideAmountsInText, setAmountsHidden, toggleAmountsHidden } from './privacy';
import { PrivacyToggleComponent } from './privacy-toggle/privacy-toggle.component';

describe('privacy mode', () => {
  afterEach(() => setAmountsHidden(false));

  it('toggles, is remembered on this device and marks <html>', () => {
    setAmountsHidden(false);
    toggleAmountsHidden();
    expect(amountsHidden()).toBeTrue();
    expect(localStorage.getItem('ft_hide_amounts')).toBe('1');
    expect(document.documentElement.classList).toContain('amounts-hidden');

    toggleAmountsHidden();
    expect(amountsHidden()).toBeFalse();
    expect(localStorage.getItem('ft_hide_amounts')).toBeNull();
    expect(document.documentElement.classList).not.toContain('amounts-hidden');
  });

  it('hides amounts but keeps empty values and text', () => {
    setAmountsHidden(true);
    expect(formatAmount('1568')).toBe(HIDDEN_AMOUNT);
    expect(new AmountPipe().transform(-20, 0)).toBe(HIDDEN_AMOUNT);
    expect(formatAmount(null)).toBe('—');
    expect(formatAmount('n/a')).toBe('n/a');

    setAmountsHidden(false);
    expect(formatAmount('1568')).toBe('1,568.00');
  });

  it('hides amounts inside server sentences, not percentages, dates or counts', () => {
    const alert = 'Groceries utilization is 90.0% (actual 1350.00 SAR, forecast 1500.00 SAR) for 2026-11.';
    expect(hideAmountsInText(alert)).toBe(
      `Groceries utilization is 90.0% (actual ${HIDDEN_AMOUNT} SAR, forecast ${HIDDEN_AMOUNT} SAR) for 2026-11.`,
    );
    expect(hideAmountsInText('Rent of 1,500 is due')).toBe(`Rent of ${HIDDEN_AMOUNT} is due`);
    expect(hideAmountsInText('Paid USD 45 today')).toBe(`Paid USD ${HIDDEN_AMOUNT} today`);
    expect(hideAmountsInText('3 payments left, 12.5% done')).toBe('3 payments left, 12.5% done');
  });

  it('privateText only rewrites while hidden', () => {
    const pipe = new PrivateTextPipe();
    expect(pipe.transform('actual 10.00 USD')).toBe('actual 10.00 USD');
    setAmountsHidden(true);
    expect(pipe.transform('actual 10.00 USD')).toBe(`actual ${HIDDEN_AMOUNT} USD`);
    expect(pipe.transform(null)).toBe('');
  });

  it('the eye button switches modes', () => {
    setAmountsHidden(false);
    const fixture = TestBed.createComponent(PrivacyToggleComponent);
    fixture.detectChanges();
    const button = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
    expect(button.getAttribute('aria-pressed')).toBe('false');
    expect(button.getAttribute('aria-label')).toBe('Hide amounts');

    button.click();
    fixture.detectChanges();
    expect(amountsHidden()).toBeTrue();
    expect(button.getAttribute('aria-pressed')).toBe('true');
    expect(button.getAttribute('aria-label')).toBe('Show amounts');
  });
});
