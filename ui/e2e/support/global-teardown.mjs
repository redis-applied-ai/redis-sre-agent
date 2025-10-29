import cleanup from './cleanup.mjs';

export default async function globalTeardown() {
  await cleanup();
}
