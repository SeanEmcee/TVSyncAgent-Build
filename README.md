# TV Sync Agent — Public Android TV Builder

Public GitHub Actions runner for the private `SeanEmcee/TVSyncAgent` Android TV app.

## One-time setup

1. Store the source in the **private** repository. For the initial milestone, upload `TVSyncAgent-native-milestone.zip` there; unpacked source files are supported as well.
2. In this public repository's **Settings → Secrets and variables → Actions**, create the secret `TVSYNC_PRIVATE_SOURCE_TOKEN`. Use a fine-grained token limited to the **private** `SeanEmcee/TVSyncAgent` repository with **Contents: Read** permission (read/write works but is not necessary for this workflow).
3. Open **Actions → Build TV Sync Agent APK → Run workflow** on `main`.

The runner checks out the private source, runs the included tests, compiles the debug Android TV APK, performs lint checks, and publishes **only** `TVSyncAgent-debug-apk` as a downloadable Actions artifact.

The workflow is manually triggered (`workflow_dispatch`) so public pull requests cannot run trusted code with the private-source credential. The secret is never printed. **Do not** commit or expose the token value in this public repository.

This is a development APK, not a verified release. Do not treat an Actions pass as proof of pixel-perfect rendering or background TV-to-TV sync on physical Chromecast hardware.
