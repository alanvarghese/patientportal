import { createHash, timingSafeEqual } from 'node:crypto';
import { NextRequest, NextResponse } from 'next/server';

function equal(a: string, b: string) {
  return timingSafeEqual(createHash('sha256').update(a).digest(), createHash('sha256').update(b).digest());
}

// Protect every route, including API requests and patient attachments.
export function proxy(request: NextRequest) {
  if (process.env.DEMO_GATE_ENABLED !== '1' && request.nextUrl.hostname !== 'patientportal.lemmanet.com') return NextResponse.next();
  const user = process.env.DEMO_GATE_USER;
  const password = process.env.DEMO_GATE_PASSWORD;
  if (!user || !password) return new NextResponse('Demo access is not configured.', { status: 503 });
  const auth = request.headers.get('authorization') || '';
  let supplied = '';
  if (auth.startsWith('Basic ')) supplied = Buffer.from(auth.slice(6), 'base64').toString('utf8');
  if (!equal(supplied, `${user}:${password}`)) return new NextResponse('Enter the shared demo credentials.', {
    status: 401,
    headers: { 'WWW-Authenticate': 'Basic realm="Practice demo", charset="UTF-8"', 'Cache-Control': 'no-store' },
  });
  const forwarded = new Headers(request.headers);
  forwarded.delete('authorization');
  const response = NextResponse.next({ request: { headers: forwarded } });
  response.headers.set('Cache-Control', 'private, no-store');
  response.headers.set('X-Robots-Tag', 'noindex, nofollow, noarchive');
  return response;
}
