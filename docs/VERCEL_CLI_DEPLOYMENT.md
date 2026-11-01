# Vercel CLI production deployment fallback

The connected deployment API can be rate-limited. The production workflow therefore includes a Vercel CLI fallback that deploys both projects from the current `main` commit when you manually run the workflow.

## Add the deployment token

1. Open https://vercel.com/account/tokens.
2. Create a token named `LIQUIDITY_NEXUS_GITHUB_ACTIONS`.
3. Scope it to the **Agus** team and ensure it can deploy both projects:
   - `liquidity-nexus-api`
   - `liquidity-nexus`
4. Copy the token once. Do not paste it into chat or commit it.
5. Open https://github.com/dilshadahmednisar123/ICT-Institutional-AI-Trading-Scanner/settings/secrets/actions.
6. Add a repository secret:
   - Name: `VERCEL_TOKEN`
   - Value: the Vercel token you just created

The workflow pins Vercel CLI to version `65.9.0`, links the two existing projects, pulls their production environment configuration, builds, and deploys the API and frontend. It does not create replacement projects.

## Run the complete release workflow

After `VERCEL_TOKEN`, `TWELVE_DATA_API_KEY`, and the four Android signing secrets are saved, open:

https://github.com/dilshadahmednisar123/ICT-Institutional-AI-Trading-Scanner/actions/workflows/ci-android.yml

Choose **Run workflow**, select `main`, and run it once. The workflow will:
1. Deploy the current `main` commit to both Vercel projects.
2. Verify production health, licensed EUR/USD and XAU/USD candles, ICT scan persistence, and history readback.
3. Run the historical backtests.
4. Build, sign, verify, and publish the Android APK to the `android-latest` GitHub Release.

A manual dispatch is necessary because adding a GitHub secret does not itself trigger a workflow.

## Quota note

Vercel may enforce plan-level deployment limits independently of the API connector. If the CLI reports that the team's daily deployment quota is exhausted, wait for the quota to reset or change the Vercel plan; a CLI token does not bypass an actual account quota.
