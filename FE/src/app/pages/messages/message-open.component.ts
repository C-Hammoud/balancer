import { Component, OnInit, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { environment } from '../../../environments/environment';

/**
 * /m/:token — the button in an email from the notification center. Records the click, then
 * opens the app page the message points to (sign-in first when needed).
 */
@Component({
  selector: 'app-message-open',
  standalone: true,
  imports: [RouterLink],
  styleUrl: '../login/login.component.scss',
  template: `
    <div class="auth-page">
      <div class="auth-card">
        <p class="eyebrow">Finance Tracker</p>
        @if (failed()) {
          <h1>Link not valid</h1>
          <p class="sub">This link is broken or no longer works.</p>
          <a class="btn primary" routerLink="/dashboard">Open Finance Tracker</a>
        } @else {
          <h1>Opening…</h1>
          <p class="sub">Taking you to Finance Tracker.</p>
        }
      </div>
    </div>
  `,
})
export class MessageOpenComponent implements OnInit {
  private http = inject(HttpClient);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  failed = signal(false);

  ngOnInit(): void {
    const token = this.route.snapshot.paramMap.get('token') ?? '';
    this.http.get<{ link: string }>(`${environment.apiUrl}/messages/open/${encodeURIComponent(token)}/`).subscribe({
      next: (r) => {
        const link = r.link && r.link.startsWith('/') ? r.link : '/dashboard';
        void this.router.navigateByUrl(link, { replaceUrl: true });
      },
      error: () => this.failed.set(true),
    });
  }
}
