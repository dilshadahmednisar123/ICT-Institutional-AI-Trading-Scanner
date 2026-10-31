# Building the Android APK (Capacitor path)

The frontend is a responsive Next.js app designed to work as a PWA and as a native Android app via Capacitor.

## Prerequisites

- Node.js 18+
- Android Studio + Android SDK
- Java 17

## Steps

### 1. Static export (recommended for Capacitor)

In `frontend/next.config.js` enable static export:

```js
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  images: { unoptimized: true },
};
module.exports = nextConfig;
```

Also set your production API URL:

```bash
# frontend/.env.production
NEXT_PUBLIC_API_URL=https://your-backend-host
```

### 2. Build the web assets

```bash
cd frontend
npm install
npm run build
# produces the `out/` directory when output: 'export' is set
```

### 3. Add Capacitor + Android platform

```bash
npm install @capacitor/core @capacitor/cli @capacitor/android
npx cap init "ICT Institutional Scanner" com.ict.institutional.scanner --web-dir out
# (skip init if capacitor.config.ts already exists)
npx cap add android
npx cap sync android
```

### 4. Open in Android Studio and build APK

```bash
npx cap open android
```

In Android Studio:

- Build → Generate Signed Bundle / APK
- Or run on emulator / device

### 5. PWA alternative (no native build)

The app is already mobile-responsive. You can install it as a PWA from Chrome on Android (Add to Home Screen) once hosted over HTTPS.

## Notes

- The backend must be reachable from the device (not `localhost`). Use a public URL or local network IP.
- Keep mode **SIGNAL ONLY**. Never embed private API keys in the mobile client.
- For production scheduler, run the Python backend on a persistent server (VPS / Railway / Render / your own box), not inside the APK.
