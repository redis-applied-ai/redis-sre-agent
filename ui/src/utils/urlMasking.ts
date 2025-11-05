/**
 * Mask username and password in Redis URL for safe display.
 *
 * @param url - Redis connection URL (e.g., redis://user:pass@host:port/db)
 * @returns Masked URL (e.g., redis://***:***@host:port/db)
 */
export function maskRedisUrl(url: string): string {
  if (!url) {
    return url;
  }

  try {
    const urlObj = new URL(url);

    // If there's a username or password, mask them
    if (urlObj.username || urlObj.password) {
      // Reconstruct URL with masked credentials
      const protocol = urlObj.protocol; // e.g., "redis:"
      const host = urlObj.hostname;
      const port = urlObj.port ? `:${urlObj.port}` : "";
      const path = urlObj.pathname;
      const search = urlObj.search;
      const hash = urlObj.hash;

      return `${protocol}//***:***@${host}${port}${path}${search}${hash}`;
    }

    return url;
  } catch (error) {
    console.warn("Failed to mask URL credentials:", error);
    return "redis://***:***@<host>:<port>";
  }
}
