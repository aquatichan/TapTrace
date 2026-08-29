import SwiftUI

@main
struct TapTraceApp: App {
    @AppStorage("hasCompletedOnboarding") private var hasCompletedOnboarding = false

    var body: some Scene {
        WindowGroup {
            Group {
                if hasCompletedOnboarding {
                    AddressView()
                } else {
                    OnboardingView(isComplete: $hasCompletedOnboarding)
                }
            }
            .tint(Color("BrandBlue"))
            .preferredColorScheme(.light)
        }
    }
}
