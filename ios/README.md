# TapTrace iOS

Native SwiftUI client for TapTrace. The app targets iPhone on iOS 17 or newer.

## Open and run

1. Open `TapTrace.xcodeproj` in Xcode.
2. Select the `TapTrace` scheme and an iPhone simulator.
3. Run the app; it uses the hosted TapTrace HTTPS backend, so the development Mac does not need to remain online.
4. Press Run in Xcode.

The API URL is configured by `TapTraceAPIBaseURL` in `TapTrace/Info.plist`. It uses the free hosted endpoint `https://taptrace-api.onrender.com`. The free service sleeps after inactivity, so the first profile can take about 50 seconds or more while it wakes; the app displays staged progress and keeps the request active.
The project is configured for Apple Developer Team `GFC3N73392`. Before TestFlight or App Store distribution, replace the local URL with the deployed HTTPS API URL.

## Regenerate the project

After changing `project.yml`, run `xcodegen generate --spec ios/project.yml` from the repository root.

## Current native flow

- Persisted two-screen onboarding
- Address validation and entry
- Live `/water-profile` API request
- Loading and explicit retry/error states
- Overview, water quality, pipe infrastructure, and recommended action sections
- Dynamic Type, VoiceOver labels, semantic colors, and native navigation
