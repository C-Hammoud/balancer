import { Injectable, signal } from '@angular/core';

export type ToastKind = 'success' | 'error' | 'info';

export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

@Injectable({ providedIn: 'root' })
export class ToastService {
  private seq = 0;
  private readonly toastsSignal = signal<Toast[]>([]);
  readonly toasts = this.toastsSignal.asReadonly();

  success(message: string, durationMs = 3000): void {
    this.push('success', message, durationMs);
  }

  error(message: string, durationMs = 4500): void {
    this.push('error', message, durationMs);
  }

  info(message: string, durationMs = 3500): void {
    this.push('info', message, durationMs);
  }

  /** Prefer API detail/field errors; fall back to a default message. */
  fromHttpError(err: unknown, fallback = 'Something went wrong.'): void {
    this.error(extractApiError(err, fallback));
  }

  dismiss(id: number): void {
    this.toastsSignal.update((list) => list.filter((t) => t.id !== id));
  }

  private push(kind: ToastKind, message: string, durationMs: number): void {
    const id = ++this.seq;
    this.toastsSignal.update((list) => [...list, { id, kind, message }]);
    window.setTimeout(() => this.dismiss(id), durationMs);
  }
}

export function extractApiError(err: unknown, fallback = 'Something went wrong.'): string {
  const e = err as { error?: unknown; message?: string; status?: number } | null;
  if (e?.status === 0) {
    return 'Cannot reach the server. Ensure the backend is running on your computer and your phone is on the same Wi‑Fi network.';
  }
  const body = e?.error;
  if (typeof body === 'string' && body.trim()) {
    return body;
  }
  if (body && typeof body === 'object') {
    const obj = body as Record<string, unknown>;
    if (typeof obj['detail'] === 'string') {
      return obj['detail'];
    }
    const parts: string[] = [];
    for (const [key, val] of Object.entries(obj)) {
      if (Array.isArray(val)) {
        parts.push(`${key}: ${val.join(', ')}`);
      } else if (typeof val === 'string') {
        parts.push(key === 'detail' ? val : `${key}: ${val}`);
      }
    }
    if (parts.length) {
      return parts.join(' · ');
    }
  }
  if (typeof e?.message === 'string' && e.message && !e.message.startsWith('Http failure')) {
    return e.message;
  }
  return fallback;
}
