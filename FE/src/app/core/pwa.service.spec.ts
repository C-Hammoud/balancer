import { clearOfflineData } from './pwa.service';

function fakeCaches(names: string[]): CacheStorage & { deleted: string[] } {
  const deleted: string[] = [];
  return {
    deleted,
    keys: async () => names,
    delete: async (name: string) => {
      deleted.push(name);
      return true;
    },
  } as unknown as CacheStorage & { deleted: string[] };
}

describe('clearOfflineData', () => {
  it('deletes only the service worker data caches, keeping the app files', async () => {
    const storage = fakeCaches([
      'ngsw:/:db:control',
      'ngsw:/:abc123:assets:app:cache',
      'ngsw:/:abc123:assets:assets:cache',
      'ngsw:/:1:data:api-read:cache',
      'ngsw:/:db:ngsw:/:1:data:api-read:age',
      'ngsw:/:db:ngsw:/:1:data:api-read:lru',
    ]);
    expect(await clearOfflineData(storage)).toBe(3);
    expect(storage.deleted).toEqual([
      'ngsw:/:1:data:api-read:cache',
      'ngsw:/:db:ngsw:/:1:data:api-read:age',
      'ngsw:/:db:ngsw:/:1:data:api-read:lru',
    ]);
  });

  it('does nothing without Cache Storage or when it fails', async () => {
    expect(await clearOfflineData(undefined)).toBe(0);
    const broken = { keys: () => Promise.reject(new Error('blocked')) } as unknown as CacheStorage;
    expect(await clearOfflineData(broken)).toBe(0);
  });
});
