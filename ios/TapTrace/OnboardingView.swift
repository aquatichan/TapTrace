import SwiftUI

struct OnboardingView: View {
    @Binding var isComplete: Bool
    @State private var page = 0

    var body: some View {
        ZStack {
            LinearGradient(colors: [.white, TapTraceTheme.surface], startPoint: .top, endPoint: .bottom).ignoresSafeArea()
            VStack(spacing: 0) {
                HStack { BrandView(compact: true); Spacer(); Button("Skip") { isComplete = true }.font(.subheadline.weight(.semibold)).foregroundStyle(TapTraceTheme.muted) }
                if page == 0 { welcome } else { howItWorks }
                Spacer(minLength: 14)
                HStack(spacing: 7) {
                    Capsule().fill(page == 0 ? Color("BrandBlue") : Color(.systemGray4)).frame(width: page == 0 ? 22 : 7, height: 7)
                    Capsule().fill(page == 1 ? Color("BrandBlue") : Color(.systemGray4)).frame(width: page == 1 ? 22 : 7, height: 7)
                }.animation(.snappy, value: page)
                Button { page == 0 ? (page = 1) : (isComplete = true) } label: {
                    Label(page == 0 ? "Continue" : "Check my water", systemImage: "chevron.right").labelStyle(.titleAndIcon)
                }.buttonStyle(PrimaryButtonStyle()).padding(.top, 16)
            }.padding(.horizontal, 24).padding(.top, 8).padding(.bottom, 14)
        }
    }

    private var welcome: some View {
        VStack(spacing: 16) {
            Image("WaterRoute").resizable().scaledToFit().frame(maxHeight: 300).padding(.horizontal, -28).accessibilityHidden(true)
            kicker("WELCOME TO TAPTRACE")
            Text("Follow your water\nfrom source to tap.").font(.largeTitle.bold()).multilineTextAlignment(.center).foregroundStyle(TapTraceTheme.ink)
            Text("Turn any U.S. address into a clear profile of its water provider, available monitoring, infrastructure context, and practical next steps.").font(.subheadline).multilineTextAlignment(.center).foregroundStyle(TapTraceTheme.muted)
        }.padding(.top, 20)
    }

    private var howItWorks: some View {
        VStack(spacing: 18) {
            kicker("HOW IT WORKS").padding(.top, 62)
            Text("Clear evidence.\nHonest limits.").font(.largeTitle.bold()).multilineTextAlignment(.center).foregroundStyle(TapTraceTheme.ink)
            Text("TapTrace separates what public records establish from what requires testing at your faucet.").font(.subheadline).multilineTextAlignment(.center).foregroundStyle(TapTraceTheme.muted)
            VStack(spacing: 12) {
                onboardingRow("mappin.and.ellipse", "Enter an address", "We match it to available official water-system records.")
                onboardingRow("drop.circle", "Review your profile", "See measurements, sources, infrastructure, and confidence.")
                onboardingRow("checklist", "Take practical action", "Get next steps based on the evidence—not generic advice.")
            }.padding(.top, 8)
        }
    }

    private func kicker(_ text: String) -> some View { Text(text).font(.caption2.bold()).tracking(1.2).foregroundStyle(Color("BrandBlue")) }
    private func onboardingRow(_ symbol: String, _ title: String, _ detail: String) -> some View {
        HStack(spacing: 14) {
            Image(systemName: symbol).font(.title3).foregroundStyle(Color("BrandBlue")).frame(width: 44, height: 44).background(TapTraceTheme.surface, in: RoundedRectangle(cornerRadius: 13))
            VStack(alignment: .leading, spacing: 4) { Text(title).font(.subheadline.bold()); Text(detail).font(.caption).foregroundStyle(TapTraceTheme.muted) }
            Spacer()
        }.padding(14).background(.background, in: RoundedRectangle(cornerRadius: 15)).overlay(RoundedRectangle(cornerRadius: 15).stroke(Color(.separator).opacity(0.35)))
    }
}

