import type { Metadata } from 'next';
import './globals.css';
import { StaffAccess } from './components/staff-access';
export const metadata: Metadata = { title: 'Practice · Team workspace', description: 'Kerala Telemedicine Platform — practice demo' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><StaffAccess>{children}</StaffAccess></body></html>;
}
