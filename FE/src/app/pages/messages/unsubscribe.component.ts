import { Component, OnInit, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { environment } from '../../../environments/environment';

/** /unsubscribe/:token — the unsubscribe link in marketing emails; no sign-in needed. */
@Component({
  selector: 'app-unsubscribe',
  standalone: true,
  imports: [RouterLink],
  styleUrl: '../login/login.component.scss',
  template: `
    <div class="auth-page">
      <div class="auth-card">
        <p class="eyebrow">Finance Tracker</p>
        @switch (state()) {
          @case ('working') {
            <h1>Unsubscribing…</h1>
          }
          @case ('done') {
            <h1>You are unsubscribed</h1>
            <p class="sub">
              You will no longer receive marketing messages. Notices about your account and the reminders
              you turned on in your profile still arrive.
            </p>
            <p class="sub">Changed your mind? Turn marketing messages back on in your <a routerLink="/profile">profile</a>.</p>
          }
          @default {
            <h1>Link not valid</h1>
            <p class="sub">
              This unsubscribe link is broken. You can turn marketing messages off in your
              <a routerLink="/profile">profile</a>.
            </p>
          }
        }
      </div>
    </div>
  `,
})
export class UnsubscribeComponent implements OnInit {
  private http = inject(HttpClient);
  private route = inject(ActivatedRoute);

  state = signal<'working' | 'done' | 'failed'>('working');

  ngOnInit(): void {
    const token = this.route.snapshot.paramMap.get('token') ?? '';
    this.http.post(`${environment.apiUrl}/messages/unsubscribe/`, { token }).subscribe({
      next: () => this.state.set('done'),
      error: () => this.state.set('failed'),
    });
  }
}
