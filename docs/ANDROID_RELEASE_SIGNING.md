# LIQUIDITY NEXUS Android release signing

The Android release workflow intentionally refuses to publish an APK unless a persistent signing identity is configured. It does not generate a throwaway key: that would make future updates fail Android's signature continuity checks.

## Create a long-lived release key

Run this on a trusted computer with JDK 17 or later. Keep the keystore and passwords in a secure password manager and offline backup. Never commit the keystore.

```bash
keytool -genkeypair -v \
  -keystore liquidity-nexus-release.jks \
  -alias liquidity-nexus \
  -keyalg RSA -keysize 4096 -validity 10000
```

Use a strong unique keystore password and key password. Do not reuse passwords from other accounts.

## Configure GitHub Actions secrets

In the repository, open **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret name | Value |
|---|---|
| `ANDROID_SIGNING_KEYSTORE_BASE64` | Base64-encoded bytes of `liquidity-nexus-release.jks` |
| `ANDROID_KEYSTORE_PASSWORD` | Keystore password |
| `ANDROID_KEY_ALIAS` | `liquidity-nexus` |
| `ANDROID_KEY_PASSWORD` | Key password |

On Linux/macOS, obtain the base64 value with:

```bash
base64 -w 0 liquidity-nexus-release.jks
```

On Windows PowerShell:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("liquidity-nexus-release.jks"))
```

Paste the output directly into the GitHub secret value field. Do not put it in a commit, issue, workflow log, chat, or public release. Store the original JKS file and passwords securely; GitHub Actions only receives the encrypted secret values.

## Build and verification

A push to `main` or a manual workflow dispatch builds the production web bundle using the configured production API URL, packages it with Capacitor, builds `assembleRelease`, signs it with the persistent keystore, verifies the APK signature and zip alignment, checks package ID `com.liquiditynexus.app`, and publishes the APK as a GitHub Actions artifact. Main-branch pushes also update the `android-latest` prerelease.

The signing key must be preserved for every future release. Losing it means existing installations cannot receive in-place signed updates.
