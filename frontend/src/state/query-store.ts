export interface QueryOptions {
  staleTime?: number;
  force?: boolean;
}

interface QueryEntry<T> {
  value?: T;
  resolvedAt: number;
  request?: Promise<T>;
}

export class QueryStore {
  readonly #entries = new Map<string, QueryEntry<unknown>>();

  async fetch<T>(
    key: string,
    loader: () => Promise<T>,
    options: QueryOptions = {},
  ): Promise<T> {
    const staleTime = options.staleTime ?? 30_000;
    const now = Date.now();
    const existing = this.#entries.get(key) as QueryEntry<T> | undefined;
    if (!options.force && existing?.request) {
      return existing.request;
    }
    if (
      !options.force
      && existing?.value !== undefined
      && now - existing.resolvedAt < staleTime
    ) {
      return existing.value;
    }

    const entry = existing ?? { resolvedAt: 0 };
    const request = loader()
      .then((value) => {
        entry.value = value;
        entry.resolvedAt = Date.now();
        entry.request = undefined;
        return value;
      })
      .catch((error: unknown) => {
        entry.request = undefined;
        throw error;
      });
    entry.request = request;
    this.#entries.set(key, entry);
    return request;
  }

  invalidate(prefix?: string): void {
    if (prefix === undefined) {
      this.#entries.clear();
      return;
    }
    for (const key of this.#entries.keys()) {
      if (key.startsWith(prefix)) {
        this.#entries.delete(key);
      }
    }
  }
}
