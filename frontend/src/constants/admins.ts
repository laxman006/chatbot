export const ADMIN_EMAILS = [
  'chaitanya.malle@cloudfuze.com',
  'laxman.kadari@cloudfuze.com',
  'nirosh.reddy@cloudfuze.com',
].map((email) => email.toLowerCase());

export function isAdminEmail(email?: string | null): boolean {
  if (!email) return false;
  return ADMIN_EMAILS.includes(email.toLowerCase());
}


