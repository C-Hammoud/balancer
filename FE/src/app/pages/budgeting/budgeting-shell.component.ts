import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-budgeting-shell',
  standalone: true,
  imports: [RouterOutlet],
  templateUrl: './budgeting-shell.component.html',
  styleUrl: './budgeting-shell.component.scss',
})
export class BudgetingShellComponent {}
