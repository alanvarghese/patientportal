import type { Metadata } from 'next';
export const metadata: Metadata = { title: 'Practice · Patient records', description: 'Patient profiles and appointment history for the local practice demo.' };
export default function PatientsLayout({ children }: { children: React.ReactNode }) { return children; }
