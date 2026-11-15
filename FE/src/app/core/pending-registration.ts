/**
 * The details of an account that was registered but not verified yet, kept for this browser tab
 * so "Wrong email? Change it" can reopen the registration form filled in. Never the password.
 */
export interface PendingRegistration {
  username: string;
  email: string;
  first_name: string;
  last_name: string;
}

const KEY = 'ft_pending_registration';

export function savePendingRegistration(data: PendingRegistration): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(data));
  } catch {
    /* storage unavailable: the form just opens empty */
  }
}

export function loadPendingRegistration(): PendingRegistration | null {
  try {
    const data = JSON.parse(sessionStorage.getItem(KEY) || 'null') as PendingRegistration | null;
    return data && data.username ? data : null;
  } catch {
    return null;
  }
}

export function clearPendingRegistration(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* nothing to clear */
  }
}
