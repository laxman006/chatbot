export const ADMIN_EMAILS = [
  'chaitanya.malle@cloudfuze.com'
].map((email) => email.toLowerCase());

export function isAdminEmail(email?: string | null): boolean {
  if (!email) return false;
  return ADMIN_EMAILS.includes(email.toLowerCase());
}


