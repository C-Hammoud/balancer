import { Component, OnInit } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { AuthService } from './core/auth.service';
import { LocaleService } from './core/locale.service';
import { ToastComponent } from './shared/toast/toast.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, ToastComponent],
  template: `
    <router-outlet />
    <app-toast />
  `,
  styles: [`:host { display: block; min-height: 100vh; }`],
})
export class AppComponent implements OnInit {
  constructor(
    private locale: LocaleService,
    private auth: AuthService
  ) {}

  ngOnInit(): void {
    this.locale.loadMeta().subscribe();
    if (this.auth.isAuthenticated()) {
      this.locale.syncFromServer().subscribe();
    }
  }
}
