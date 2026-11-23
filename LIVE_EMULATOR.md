# TV Sync — Live Google TV Emulator

**Offline — no active interactive session confirmed.**

To start a new temporary session:

1. In this public repository's [Actions secrets](https://github.com/SeanEmcee/TVSyncAgent-Build/settings/secrets/actions), save your own email address (not a token) under the name `TVSYNC_EMULATOR_EMAIL`. Do not share the value in chat or put it into source code.
2. Open [TV Sync Interactive Google TV Emulator](https://github.com/SeanEmcee/TVSyncAgent-Build/actions/workflows/live-emulator.yml), choose **Run workflow** on `main`.
3. Once the emulator boots, revisit this page for the temporary **Open interactive emulator** link. GitHub also announces the URL in that run's live logs.
4. Cloudflare will send a one-time PIN to the approved email address before allowing access.

The emulator runs on an ephemeral GitHub Actions runner, has only synthetic TV files, and does not connect to either physical Chromecast. Sessions expire and may end early if the GitHub runner stops. The APK is the previously verified debug build; this is not yet proof of visual pixel parity.
