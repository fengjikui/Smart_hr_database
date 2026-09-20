import type { NextConfig } from 'next';
const nextConfig: NextConfig = {
  // 旧书签仅重定向到当前页面，不保留另一套界面实现。
  async redirects() {
    return [
      { source: '/demo', destination: '/', permanent: true },
      { source: '/demo/debug', destination: '/debug', permanent: true },
    ];
  },
  async headers() {
    return ['/', '/:path*'].map((source) => ({
      source,
      headers: [
        { key: 'X-Content-Type-Options', value: 'nosniff' },
        { key: 'X-Frame-Options', value: 'DENY' },
        { key: 'Referrer-Policy', value: 'no-referrer' },
        {
          key: 'Content-Security-Policy',
          value:
            "frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'",
        },
        {
          key: 'Permissions-Policy',
          value: 'camera=(), microphone=(), geolocation=()',
        },
      ],
    }));
  },
};
export default nextConfig;
