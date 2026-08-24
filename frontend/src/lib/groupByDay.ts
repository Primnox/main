

export function groupByDay(rows: any[]): [string, any[]][] {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const day = 86_400_000;

  const bucket = (ts: number): string => {
    if (!ts) return 'Earlier';
    if (ts >= startOfToday) return 'Today';
    if (ts >= startOfToday - day) return 'Yesterday';
    if (ts >= startOfToday - 7 * day) return 'Previous 7 days';
    if (ts >= startOfToday - 30 * day) return 'Previous 30 days';
    return 'Earlier';
  };

  const order = ['Today', 'Yesterday', 'Previous 7 days', 'Previous 30 days', 'Earlier'];
  const groups = new Map<string, any[]>();
  for (const c of rows) {
    const key = bucket(c.updated_at ?? c.created_at ?? 0);
    (groups.get(key) ?? groups.set(key, []).get(key)!).push(c);
  }
  return order.filter(k => groups.has(k)).map(k => [k, groups.get(k)!] as [string, any[]]);
}

