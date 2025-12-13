const base = process.env.API_BASE_URL || 'http://localhost:8000/api/v1';

const E2E_PATTERNS = [/^e2e\b/i, /^e2e\s+hello/i, /^e2e\s+streaming/i, /^e2e\s+persistence/i, /^e2e\s+schedule/i, /^e2e\s+update\s+test/i];

const withinHours = (iso, hours = 72) => {
  try { return Date.now() - new Date(iso).getTime() < hours * 3600 * 1000; } catch { return false; }
};

const matchesE2E = (subject) => subject && E2E_PATTERNS.some((re) => re.test(subject));

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

async function listSchedules() {
  const res = await fetch(`${base}/schedules/`);
  if (!res.ok) throw new Error(`Failed to list schedules: ${res.status} ${res.statusText}`);
  return res.json();
}

async function deleteSchedule(id) {
  const res = await fetch(`${base}/schedules/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to delete schedule ${id}: ${res.status} ${res.statusText}`);
}

async function cleanupSchedules() {
  try {
    const schedules = await listSchedules();
    let deleted = 0;
    for (const s of schedules) {
      const name = s.name || '';
      const recent = withinHours(s.updated_at || s.created_at || '');
      if (matchesE2E(name) || (name.toLowerCase().startsWith('e2e ') && recent)) {
        try { await deleteSchedule(s.id); deleted++; }
        catch (e) { console.warn(`Could not delete schedule ${s.id}: ${e.message}`); }
      }
    }
    console.log(`[global cleanup] Deleted ${deleted} E2E schedules`);
  } catch (e) {
    console.warn(`[global cleanup] Schedule cleanup failed: ${e.message}`);
  }
}

export default async function cleanup() {
  // Clean up threads
  try {
    const threads = await listThreads(1000);
    let deleted = 0;
    for (const t of threads) {
      const subj = t.subject || '';
      const recent = withinHours(t.updated_at || t.created_at || '');
      if (matchesE2E(subj) || (subj.toLowerCase().startsWith('e2e ') && recent)) {
        try { await deleteThread(t.thread_id); deleted++; }
        catch (e) { console.warn(`Could not delete ${t.thread_id}: ${e.message}`); }
      }
    }
    console.log(`[global cleanup] Deleted ${deleted} E2E threads`);
  } catch (e) {
    console.warn(`[global cleanup] Thread cleanup failed: ${e.message}`);
  }

  // Clean up schedules
  await cleanupSchedules();
}
