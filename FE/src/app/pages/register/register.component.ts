import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/auth.service';
import {
  clearPendingRegistration,
  loadPendingRegistration,
  savePendingRegistration,
} from '../../core/pending-registration';
import { ToastService } from '../../core/toast.service';

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink],
  templateUrl: './register.component.html',
  styleUrl: './register.component.scss',
})
export class RegisterComponent implements OnInit {
  private fb = inject(FormBuilder);
  private auth = inject(AuthService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);
  private toast = inject(ToastService);

  loading = signal(false);
  /** Fixing the details of an account that is registered but not verified yet. */
  editing = signal(false);

  form = this.fb.nonNullable.group({
    username: ['', Validators.required],
    email: ['', [Validators.required, Validators.email]],
    first_name: [''],
    last_name: [''],
    password: ['', [Validators.required, Validators.minLength(8)]],
    password_confirm: ['', Validators.required],
  });

  ngOnInit(): void {
    const params = this.route.snapshot.queryParamMap;
    const pending = params.get('edit') ? loadPendingRegistration() : null;
    if (pending) {
      this.form.patchValue(pending);
      // The username identifies the pending account; a different one would create a second account.
      this.form.controls.username.disable();
      this.editing.set(true);
      return;
    }
    const prefill = params.get('email');
    if (prefill) {
      this.form.patchValue({ email: prefill });
    }
  }

  /** Leave edit mode and register a completely new account. */
  startOver(): void {
    clearPendingRegistration();
    this.editing.set(false);
    this.form.reset();
    this.form.controls.username.enable();
    this.router.navigate([], { queryParams: {}, replaceUrl: true });
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.toast.error('Please fill in the required fields.');
      return;
    }
    const raw = this.form.getRawValue();
    if (raw.password !== raw.password_confirm) {
      this.toast.error('Passwords do not match.');
      return;
    }
    this.loading.set(true);
    this.auth.register(raw).subscribe({
      next: (res) => {
        this.loading.set(false);
        if (res.verification_required) {
          const email = res.email || raw.email;
          savePendingRegistration({
            username: raw.username,
            email,
            first_name: raw.first_name,
            last_name: raw.last_name,
          });
          this.toast.success(res.detail);
          this.router.navigate(['/check-email'], { queryParams: { email } });
          return;
        }
        clearPendingRegistration();
        this.toast.success('Account created successfully.');
        this.router.navigate(['/dashboard'], { queryParams: { setup: 'accounts' } });
      },
      error: (err) => {
        this.loading.set(false);
        const fallback = this.editing()
          ? 'Could not update your details. Use the same password you chose when you registered.'
          : 'Could not create account.';
        this.toast.fromHttpError(err, fallback);
      },
    });
  }
}
