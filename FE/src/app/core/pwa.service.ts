/**
 * Offline copies of API responses kept by the service worker (ngsw-config.json "dataGroups").
 *
 * The service worker stores responses by URL and ignores the Authorization header, so the next
 * person signing in on the same device could be shown the previous user's saved data while
 * offline. Clear those copies whenever the session ends or a new one starts. App files (the
 * "assets" caches) stay, so the app still opens offline.
 */
export async function clearOfflineData(storage: CacheStorage | undefined = globalThis.caches): Promise<number> {
  if (!storage) return 0;
  try {
    const names = await storage.keys();
    // Angular names them "ngsw:<scope>:<version>:data:<group>:cache" (and ":age"/":lru" tables).
    const dataCaches = names.filter((name) => name.includes(':data:'));
    await Promise.all(dataCaches.map((name) => storage.delete(name)));
    return dataCaches.length;
  } catch {
    return 0; // Cache Storage unavailable (private mode, old browser): nothing was saved anyway.
  }
}
