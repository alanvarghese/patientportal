import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Practice · Patient registration & booking',
  description: 'Register a fictional patient and book a demo appointment with the practice.',
};

export default function BookingLayout({ children }: { children: React.ReactNode }) {
  return children;
}
