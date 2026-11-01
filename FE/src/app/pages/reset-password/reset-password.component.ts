import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/auth.service';
import { ToastService } from '../../core/toast.service';

@Component({
  selector: 'app-reset-password',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink],
  templateUrl: './reset-password.component.html',
  styleUrl: '../login/login.component.scss',
})
export class ResetPasswordComponent implements OnInit {
  private fb = inject(FormBuilder);
  private auth = inject(AuthService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);
  private toast = inject(ToastService);

  loading = signal(false);
  done = signal(false);
  uid = '';
  token = '';

  form = this.fb.nonNullable.group({
    password: ['', Validators.required],
    password_confirm: ['', Validators.required],
  });

  ngOnInit(): void {
    this.uid = this.route.snapshot.queryParamMap.get('uid') || '';
    this.token = this.route.snapshot.queryParamMap.get('token') || '';
    if (!this.uid || !this.token) {
      this.toast.error('Invalid reset link. Request a new one.');
    }
  }

  get linkValid(): boolean {
    return !!this.uid && !!this.token;
  }

  submit(): void {
    if (!this.linkValid) {
      this.toast.error('Invalid reset link.');
      return;
    }
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.toast.error('Enter and confirm your new password.');
      return;
    }
    const raw = this.form.getRawValue();
    if (raw.password !== raw.password_confirm) {
      this.toast.error('Passwords do not match.');
      return;
    }
    this.loading.set(true);
    this.auth
      .confirmPasswordReset({
        uid: this.uid,
        token: this.token,
        password: raw.password,
        password_confirm: raw.password_confirm,
      })
      .subscribe({
        next: (res) => {
          this.loading.set(false);
          this.done.set(true);
          this.toast.success(res.detail);
        },
        error: (err) => {
          this.loading.set(false);
          this.toast.fromHttpError(err, 'Could not reset password. The link may have expired.');
        },
      });
  }

  goLogin(): void {
    this.router.navigate(['/login']);
  }
}
