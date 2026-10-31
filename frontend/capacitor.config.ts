import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.ict.institutional.scanner',
  appName: 'ICT Institutional Scanner',
  webDir: 'out',
  server: {
    // For development you can point to local Next.js; for production use static export
    androidScheme: 'https',
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 2000,
      backgroundColor: '#0b0f14',
    },
  },
};

export default config;
