import type { CapacitorConfig } from '@capacitor/cli';
const config: CapacitorConfig = {
  appId: 'com.liquiditynexus.app',
  appName: 'LIQUIDITY NEXUS',
  webDir: 'out',
  server: { androidScheme: 'https' },
  plugins: { SplashScreen: { launchShowDuration: 1800, backgroundColor: '#07111f' } },
};
export default config;
