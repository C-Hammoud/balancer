import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/auth.service';
import { ToastService, extractApiError } from '../../core/toast.service';

@Component({
  selector: 'app-verify-email',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './verify-email.component.html',
  styleUrl: './verify-email.component.scss',
})
export class VerifyEmailComponent implements OnInit {
  private auth = inject(AuthService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private toast = inject(ToastService);

  loading = signal(true);
  done = signal(false);
  failed = signal(false);
  errorMessage = signal('');
  uid = '';
  token = '';

  private verificationStarted = false;

  ngOnInit(): void {
    // Drop stale tokens so guards/interceptors do not redirect away before verify runs.
    this.auth.clearSession();

    this.route.queryParamMap.subscribe((params) => {
      if (params.get('verified') === '1') {
        this.loading.set(false);
        this.done.set(true);
        return;
      }

      this.uid = params.get('uid') || '';
      this.token = params.get('token') || '';
      const errorParam = params.get('error');

      if (errorParam) {
        this.loading.set(false);
        this.failed.set(true);
        this.errorMessage.set(decodeURIComponent(errorParam));
        return;
      }

      if (!this.uid || !this.token) {
        this.loading.set(false);
        this.failed.set(true);
        this.errorMessage.set('This verification link is invalid or incomplete.');
        return;
      }

      if (this.verificationStarted) {
        return;
      }
      this.verificationStarted = true;
      this.runVerification();
    });
  }

  private runVerification(): void {
    this.loading.set(true);
    this.failed.set(false);
    this.done.set(false);

    this.auth.verifyEmail(this.uid, this.token).subscribe({
      next: (res) => {
        this.loading.set(false);
        if (res.email_verified) {
          this.done.set(true);
          this.toast.success(res.detail);
          window.setTimeout(() => {
            this.router.navigate(['/login'], { queryParams: { verified: '1' } });
          }, 1800);
          return;
        }
        this.failed.set(true);
        this.errorMessage.set(res.detail || 'Verification did not complete.');
      },
      error: (err) => {
        this.loading.set(false);
        this.failed.set(true);
        this.errorMessage.set(extractApiError(err, 'Could not verify email. The link may have expired.'));
      },
    });
  }

  goToLogin(): void {
    this.router.navigate(['/login'], {
      queryParams: this.done() ? { verified: '1' } : {},
    });
  }
}
