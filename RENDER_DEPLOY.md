# Free Render deployment

TapTrace includes a Render Blueprint in `render.yaml`. It creates one free Docker
web service with a permanent HTTPS `onrender.com` address.

## Deploy

1. Push the current repository to GitHub.
2. Open:
   `https://dashboard.render.com/blueprint/new?repo=https://github.com/aquatichan/TapTrace`
3. Sign in to Render with GitHub and authorize the TapTrace repository.
4. Keep the `Free` service plan and apply the Blueprint.
5. Wait for the first build. It downloads and checksum-verifies the versioned
   national runtime data, then downloads Houston and DC property inventories from
   their official public endpoints.
6. Open `https://<service-name>.onrender.com/health`. A ready service returns
   `"status":"ok"` with all three national registry dependencies set to `true`.
7. Replace `TapTraceAPIBaseURL` in `ios/TapTrace/Info.plist` with that HTTPS URL,
   rebuild, and run the nationwide smoke tests.

## Free-service behavior

Render may suspend the service after 15 minutes without traffic. The iOS client
allows up to two minutes, displays staged progress, and automatically retries one
transient cold-start failure. The profile request uses POST so the submitted address
does not appear in the URL or normal proxy query logs.

The service bundles read-only national registries. Ephemeral response caches may be
lost when Render restarts without affecting the authoritative profile data.
