import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/auth.service';
import { ToastService } from '../../core/toast.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
})
export class LoginComponent implements OnInit {
  private fb = inject(FormBuilder);
  private auth = inject(AuthService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);
  private toast = inject(ToastService);

  loading = signal(false);
  needsVerification = signal(false);
  pendingEmail = signal('');
  verifiedBanner = signal(false);
  expiredBanner = signal(false);
  showPassword = signal(false);

  form = this.fb.nonNullable.group({
    username: ['', Validators.required],
    password: ['', Validators.required],
  });

  ngOnInit(): void {
    if (this.route.snapshot.queryParamMap.get('verified') === '1') {
      this.verifiedBanner.set(true);
      this.toast.success('Email verified! Sign in with your username and password.');
    }
    if (this.route.snapshot.queryParamMap.get('expired') === '1') {
      this.expiredBanner.set(true);
    }
  }

  /** Page to return to after signing in: only paths inside this app (no external redirects). */
  private returnUrl(): string {
    const url = this.route.snapshot.queryParamMap.get('returnUrl') || '';
    const safe = url.startsWith('/') && !url.startsWith('//') && !url.startsWith('/login');
    return safe ? url : '/dashboard';
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.toast.error('Enter username and password.');
      return;
    }
    this.loading.set(true);
    this.needsVerification.set(false);
    this.verifiedBanner.set(false);
    const { username, password } = this.form.getRawValue();
    this.auth.login(username, password).subscribe({
      next: () => {
        this.loading.set(false);
        this.toast.success('Signed in successfully.');
        this.router.navigateByUrl(this.returnUrl());
      },
      error: (err) => {
        this.loading.set(false);
        const body = (err as { error?: { code?: string; detail?: string } })?.error;
        if (body?.code === 'email_not_verified') {
          this.needsVerification.set(true);
          this.pendingEmail.set(username.includes('@') ? username : '');
          this.toast.error(body.detail || 'Please verify your email before signing in.');
          return;
        }
        this.toast.fromHttpError(err, 'Invalid username or password.');
      },
    });
  }

  resendVerification(): void {
    const email = this.pendingEmail();
    const username = this.form.getRawValue().username;
    const target = email || (username.includes('@') ? username : '');
    if (!target) {
      this.router.navigate(['/check-email']);
      return;
    }
    this.loading.set(true);
    this.auth.resendVerificationEmail(target).subscribe({
      next: (res) => {
        this.loading.set(false);
        this.toast.success(res.detail);
        this.router.navigate(['/check-email'], { queryParams: { email: target } });
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not resend verification email.');
      },
    });
  }
}
