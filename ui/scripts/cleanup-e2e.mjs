// Cleanup script for E2E-created threads in the Redis SRE Agent backend
// Usage:
//   API_BASE_URL=http://localhost:8000/api/v1 node scripts/cleanup-e2e.mjs
// Defaults to localhost if API_BASE_URL not set

const base = process.env.API_BASE_URL || 'http://localhost:8000/api/v1';

const E2E_PATTERNS = [
  /^e2e\b/i,
  /^e2e\s+hello/i,
  /^e2e\s+streaming/i,
  /^e2e\s+persistence/i,
];

const withinHours = (iso, hours = 24) => {
  try {
    const t = new Date(iso).getTime();
    const now = Date.now();
    return now - t < hours * 3600 * 1000;
  } catch {
    return false;
  }
};

const matchesE2E = (subject) => {
  if (!subject) return false;
  return E2E_PATTERNS.some((re) => re.test(subject));
};

async function listThreads(limit = 500) {
  const url = new URL(`${base}/threads`);
  url.searchParams.set('limit', String(limit));
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to list threads: ${res.status} ${res.statusText}`);
  return res.json();
}

async function deleteThread(id) {
  const res = await fetch(`${base}/threads/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to delete ${id}: ${res.status} ${res.statusText}`);
}

(async () => {
  try {
    const threads = await listThreads(1000);
    let deleted = 0;
    for (const t of threads) {
      const subj = t.subject || '';
      const recent = withinHours(t.updated_at || t.created_at || '', 72);
      if (matchesE2E(subj) || (subj.toLowerCase().startsWith('e2e ') && recent)) {
        try {
          await deleteThread(t.thread_id);
          deleted++;
          console.log(`Deleted E2E thread: ${t.thread_id} (${subj})`);
        } catch (e) {
          console.warn(`Could not delete ${t.thread_id}: ${e.message}`);
        }
      }
    }
    console.log(`Cleanup complete. Deleted ${deleted} threads.`);
  } catch (e) {
    console.error(`Cleanup failed: ${e.message}`);
    process.exitCode = 1;
  }
})();
