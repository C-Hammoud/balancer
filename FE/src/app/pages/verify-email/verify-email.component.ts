import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/auth.service';
import { clearPendingRegistration } from '../../core/pending-registration';
import { extractApiError } from '../../core/toast.service';

/** loading → activated (first time) | already (link opened again) | failed */
type VerifyState = 'loading' | 'activated' | 'already' | 'failed';

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

  state = signal<VerifyState>('loading');
  errorMessage = signal('');
  uid = '';
  token = '';

  private verificationStarted = false;

  ngOnInit(): void {
    // Drop stale tokens so guards/interceptors do not redirect away before verify runs.
    this.auth.clearSession();

    this.route.queryParamMap.subscribe((params) => {
      if (params.get('verified') === '1') {
        this.state.set('activated');
        return;
      }

      this.uid = params.get('uid') || '';
      this.token = params.get('token') || '';
      const errorParam = params.get('error');

      if (errorParam) {
        this.fail(decodeURIComponent(errorParam));
        return;
      }

      if (!this.uid || !this.token) {
        this.fail('This verification link is invalid or incomplete.');
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
    this.state.set('loading');
    this.auth.verifyEmail(this.uid, this.token).subscribe({
      next: (res) => {
        if (res.email_verified) {
          clearPendingRegistration();
          this.state.set(res.already_verified ? 'already' : 'activated');
          return;
        }
        this.fail(res.detail || 'Verification did not complete.');
      },
      error: (err) => this.fail(extractApiError(err, 'Could not verify email. The link may have expired.')),
    });
  }

  private fail(message: string): void {
    this.errorMessage.set(message);
    this.state.set('failed');
  }

  goToLogin(): void {
    const active = this.state() === 'activated' || this.state() === 'already';
    this.router.navigate(['/login'], { queryParams: active ? { verified: '1' } : {} });
  }
}
