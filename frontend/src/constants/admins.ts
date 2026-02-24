import type { User } from '@/types/chat';

/**
 * Admin status comes from the backend only (GET /user/profile or OAuth callback).
 * Never ship a list of admin emails to the client.
 */
export function isAdmin(user: User | null | undefined): boolean {
  return !!user?.is_admin;
}
