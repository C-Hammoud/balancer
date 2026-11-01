import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/auth.service';
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

  form = this.fb.nonNullable.group({
    username: ['', Validators.required],
    email: ['', [Validators.required, Validators.email]],
    first_name: [''],
    last_name: [''],
    password: ['', [Validators.required, Validators.minLength(8)]],
    password_confirm: ['', Validators.required],
  });

  ngOnInit(): void {
    const prefill = this.route.snapshot.queryParamMap.get('email');
    if (prefill) {
      this.form.patchValue({ email: prefill });
    }
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
          this.toast.success(res.detail);
          this.router.navigate(['/check-email'], {
            queryParams: { email: res.email || raw.email },
          });
          return;
        }
        this.toast.success('Account created successfully.');
        this.router.navigate(['/dashboard'], { queryParams: { setup: 'accounts' } });
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not create account.');
      },
    });
  }
}
