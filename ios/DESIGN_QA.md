# TapTrace iOS visual QA

Status: **Passed** on iPhone 16 Pro Max simulator (iOS 26.5).

## Verified journey

- Premium onboarding screens render from the approved final plates.
- Apple Maps autocomplete accepts partial addresses and resolves a full street, city, state, and ZIP.
- The resolved address starts the live backend request.
- Premium loading animation remains visible while the free backend wakes and builds the profile.
- The live Houston test address returned a completed profile.
- Profile navigation opens water quality, pipes, actions, roadmap, contact, and filter screens.
- The roadmap opens a profile-matched filter recommendation.
- The primary filter button opens the real Brita product page; alternatives open the NSF certified-products directory.
- The contact action copies the prepared request and opens the user's email composer without sending automatically.

## Visual comparison

The approved generated images are shipped as source-of-truth Xcode image assets. Simulator rendering was compared side-by-side with the approved filter reference at the same aspect ratio. Content, color, typography, imagery, spacing, borders, and shadows are preserved by using the approved plates directly. The only variable visual layer is Apple's system-owned status bar and device chrome.

## Build verification

`xcodebuild` completed successfully for the iOS Simulator target after the final safe-area alignment pass.
