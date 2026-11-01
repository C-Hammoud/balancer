import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { AuthService } from '../../core/auth.service';
import { LocaleService } from '../../core/locale.service';
import { ToastService } from '../../core/toast.service';

@Component({
  selector: 'app-profile',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink],
  templateUrl: './profile.component.html',
  styleUrl: './profile.component.scss',
})
export class ProfileComponent implements OnInit {
  private auth = inject(AuthService);
  private locale = inject(LocaleService);
  private fb = inject(FormBuilder);
  private toast = inject(ToastService);

  readonly user = this.auth.user;
  readonly currencyOptions = this.locale.currencies;
  saving = signal(false);
  resending = signal(false);
  emailVerified = signal(true);

  form = this.fb.nonNullable.group({
    first_name: [''],
    last_name: [''],
    email: ['', Validators.email],
    default_currency: ['USD', Validators.required],
    timezone: [''],
    country: [''],
    notify_plan_updates: [true],
    savings_target_pct: [20, [Validators.min(0), Validators.max(90)]],
  });

  ngOnInit(): void {
    this.locale.loadMeta().subscribe();
    this.loadProfile();
  }

  loadProfile(): void {
    this.auth.loadMe().subscribe({
      next: (u) => {
        this.emailVerified.set(!!u.email_verified);
        const prefs = this.locale.preferences();
        this.form.reset({
          first_name: u.first_name || '',
          last_name: u.last_name || '',
          email: u.email || '',
          default_currency: u.default_currency || prefs.default_currency || 'USD',
          timezone: u.timezone || prefs.timezone || this.locale.detectTimezone(),
          country: u.country || prefs.country || '',
          notify_plan_updates: u.notify_plan_updates ?? true,
          savings_target_pct: u.savings_target_pct ?? 20,
        });
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not load profile.'),
    });
  }

  useDetectedTimezone(): void {
    this.form.patchValue({ timezone: this.locale.detectTimezone() });
  }

  resendVerification(): void {
    const email = this.form.getRawValue().email || this.user()?.email || '';
    if (!email) {
      this.toast.error('Add an email address first.');
      return;
    }
    this.resending.set(true);
    this.auth.resendVerificationEmail(email).subscribe({
      next: (res) => {
        this.resending.set(false);
        this.toast.success(res.detail);
      },
      error: (err) => {
        this.resending.set(false);
        this.toast.fromHttpError(err, 'Could not send verification email.');
      },
    });
  }

  save(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.toast.error('Check the form fields.');
      return;
    }
    const raw = this.form.getRawValue();
    this.saving.set(true);
    this.locale
      .savePreferences({
        first_name: raw.first_name,
        last_name: raw.last_name,
        email: raw.email,
        default_currency: raw.default_currency,
        timezone: raw.timezone,
        country: raw.country,
        notify_plan_updates: raw.notify_plan_updates,
        savings_target_pct: Number(raw.savings_target_pct),
      })
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.toast.success(
            `Profile saved. Reports and new entries default to ${raw.default_currency}.`
          );
          this.auth.loadMe().subscribe({
            next: (u) => this.emailVerified.set(!!u.email_verified),
          });
        },
        error: (err) => {
          this.saving.set(false);
          this.toast.fromHttpError(err, 'Could not save profile.');
        },
      });
  }
}
