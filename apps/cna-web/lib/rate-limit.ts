// Simple in-memory rate limiter for Next.js Server Actions (OWA-02)
// Since Server Actions execute in the Node.js runtime, this Map persists across requests.
const rateLimitMap = new Map<string, number[]>();

/**
 * Checks if a user has exceeded their rate limit for a specific action.
 * Default: 5 requests per 60 seconds.
 */
export async function checkRateLimit(
  userId: string,
  actionName: string,
  limit: number = 5,
  windowMs: number = 60000
): Promise<boolean> {
  const key = `${userId}:${actionName}`;
  const now = Date.now();
  const timestamps = rateLimitMap.get(key) || [];

  // Filter out timestamps older than the window
  const activeTimestamps = timestamps.filter((t) => now - t < windowMs);

  if (activeTimestamps.length >= limit) {
    return false;
  }

  activeTimestamps.push(now);
  rateLimitMap.set(key, activeTimestamps);
  return true;
}
