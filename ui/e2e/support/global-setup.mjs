import cleanup from './cleanup.mjs';

export default async function globalSetup() {
  await cleanup();
}
