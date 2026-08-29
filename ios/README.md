# TapTrace iOS

Native SwiftUI client for TapTrace. The app targets iPhone on iOS 17 or newer.

## Open and run

1. Open `TapTrace.xcodeproj` in Xcode.
2. Select the `TapTrace` scheme and an iPhone simulator.
3. Keep the TapTrace backend and its ngrok tunnel running on the host Mac.
4. Press Run in Xcode.

The API URL is configured by `TapTraceAPIBaseURL` in `TapTrace/Info.plist`. It currently uses the permanent HTTPS ngrok endpoint `https://cycle-chug-nervy.ngrok-free.dev`.
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
