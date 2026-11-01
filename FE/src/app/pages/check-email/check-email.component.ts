import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { AuthService } from '../../core/auth.service';
import { ToastService } from '../../core/toast.service';

@Component({
  selector: 'app-check-email',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink],
  templateUrl: './check-email.component.html',
  styleUrl: '../login/login.component.scss',
})
export class CheckEmailComponent {
  private fb = inject(FormBuilder);
  private auth = inject(AuthService);
  private route = inject(ActivatedRoute);
  private toast = inject(ToastService);

  loading = signal(false);
  sent = signal(false);
  email = this.route.snapshot.queryParamMap.get('email') || '';

  form = this.fb.nonNullable.group({
    email: [this.email, [Validators.required, Validators.email]],
  });

  resend(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.toast.error('Enter the email you used to register.');
      return;
    }
    this.loading.set(true);
    this.auth.resendVerificationEmail(this.form.getRawValue().email).subscribe({
      next: (res) => {
        this.loading.set(false);
        this.sent.set(true);
        this.toast.success(res.detail);
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not send verification email.');
      },
    });
  }
}
