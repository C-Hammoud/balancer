/** Tabs of the phone bottom bar (the + in the middle opens Quick add and is never "current"). */
export type BottomTab = 'home' | 'utilization' | 'budgeting' | 'profile' | null;

/**
 * Which bottom-bar tab a URL belongs to. Every budgeting page except Utilization lights up
 * "Budgeting", so the bar always shows the section the user is in.
 */
export function bottomTab(url: string): BottomTab {
  const path = (url || '/').split(/[?#]/)[0].replace(/\/+$/, '') || '/';
  if (path === '/' || path === '/dashboard' || path.startsWith('/dashboard/')) return 'home';
  if (path === '/budgeting/utilization' || path.startsWith('/budgeting/utilization/')) return 'utilization';
  if (path === '/budgeting' || path.startsWith('/budgeting/')) return 'budgeting';
  if (path === '/profile' || path.startsWith('/profile/')) return 'profile';
  return null;
}
