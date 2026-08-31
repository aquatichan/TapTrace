import SwiftUI

struct OnboardingView: View {
    @Binding var isComplete: Bool
    @State private var page = 0
    @State private var animate = false

    var body: some View {
        ZStack {
            TapTraceTheme.pageBackground.ignoresSafeArea()
            Circle().fill(TapTraceTheme.cyan.opacity(0.13)).frame(width: 260).blur(radius: 18)
                .offset(x: animate ? 150 : 105, y: animate ? -330 : -290)
            Circle().fill(Color("BrandBlue").opacity(0.09)).frame(width: 220).blur(radius: 24)
                .offset(x: animate ? -145 : -105, y: animate ? 350 : 310)
            VStack(spacing: 0) {
                HStack {
                    BrandView(compact: true); Spacer()
                    Button("Skip") { isComplete = true }.font(.subheadline.weight(.semibold)).foregroundStyle(TapTraceTheme.muted)
                }
                TabView(selection: $page) { promise.tag(0); translation.tag(1); evidence.tag(2) }
                    .tabViewStyle(.page(indexDisplayMode: .never))
                HStack(spacing: 7) {
                    ForEach(0..<3) { index in
                        Capsule().fill(index == page ? Color("BrandBlue") : Color(.systemGray4))
                            .frame(width: index == page ? 24 : 7, height: 7)
                    }
                }.animation(.snappy, value: page)
                Button {
                    if page < 2 { withAnimation(.snappy) { page += 1 } } else { isComplete = true }
                } label: { Label(page == 2 ? "Check my water" : "Show me", systemImage: page == 2 ? "drop.fill" : "arrow.right") }
                    .buttonStyle(PrimaryButtonStyle()).padding(.top, 18)
            }.padding(.horizontal, 24).padding(.top, 8).padding(.bottom, 14)
        }
        .onAppear { withAnimation(.easeInOut(duration: 4).repeatForever(autoreverses: true)) { animate = true } }
    }

    private var promise: some View {
        VStack(spacing: 16) {
            Spacer(minLength: 12)
            Image("WaterRoute").resizable().scaledToFit().frame(maxHeight: 290)
                .scaleEffect(animate ? 1.025 : 0.98).accessibilityHidden(true)
            kicker("WATER ANSWERS YOU CAN USE")
            Text("One address.\nOne clear water plan.").font(.largeTitle.bold()).multilineTextAlignment(.center).foregroundStyle(TapTraceTheme.ink)
            Text("We turn official records into simple language, show what matters, and give you a next step.")
                .font(.subheadline).multilineTextAlignment(.center).foregroundStyle(TapTraceTheme.muted)
            Spacer(minLength: 10)
        }
    }

    private var translation: some View {
        VStack(spacing: 18) {
            Spacer(minLength: 30); kicker("NO SCIENCE DEGREE REQUIRED")
            Text("See the meaning,\nnot a wall of numbers.").font(.largeTitle.bold()).multilineTextAlignment(.center).foregroundStyle(TapTraceTheme.ink)
            HStack(spacing: 8) {
                miniCard("eye.fill", "What was found", TapTraceTheme.cyan)
                Image(systemName: "arrow.right").foregroundStyle(TapTraceTheme.muted)
                miniCard("heart.text.square.fill", "Why it matters", .orange)
                Image(systemName: "arrow.right").foregroundStyle(TapTraceTheme.muted)
                miniCard("checkmark.circle.fill", "What to do", .green)
            }.padding(.vertical, 18)
            Text("Every result comes with a plain-English explanation, possible health concerns, and practical ways to reduce exposure.")
                .font(.subheadline).multilineTextAlignment(.center).foregroundStyle(TapTraceTheme.muted)
            Spacer(minLength: 20)
        }
    }

    private var evidence: some View {
        VStack(spacing: 18) {
            Spacer(minLength: 28); kicker("CLEAR ANSWERS, HONEST LIMITS")
            Text("Know what is measured—and what is not.").font(.largeTitle.bold()).multilineTextAlignment(.center).foregroundStyle(TapTraceTheme.ink)
            VStack(spacing: 0) {
                evidenceRow("building.2.fill", "Your water provider", "Official system tests and notices", .blue, true)
                evidenceRow("pipe.and.drop.fill", "Your service line", "Property record when one exists", .cyan, true)
                evidenceRow("house.fill", "Your faucet", "Only a home test can confirm this", .indigo, false)
            }.padding(18).background(.white.opacity(0.84), in: RoundedRectangle(cornerRadius: 24))
                .overlay(RoundedRectangle(cornerRadius: 24).stroke(TapTraceTheme.border.opacity(0.65)))
            Text("TapTrace never turns missing data into false certainty.").font(.subheadline.weight(.semibold)).multilineTextAlignment(.center).foregroundStyle(TapTraceTheme.muted)
            Spacer(minLength: 20)
        }
    }

    private func kicker(_ text: String) -> some View { Text(text).font(.caption2.bold()).tracking(1.25).foregroundStyle(Color("BrandBlue")) }
    private func miniCard(_ symbol: String, _ text: String, _ color: Color) -> some View {
        VStack(spacing: 9) { Image(systemName: symbol).font(.title2).foregroundStyle(color); Text(text).font(.caption2.weight(.semibold)).multilineTextAlignment(.center).foregroundStyle(TapTraceTheme.ink) }
            .frame(maxWidth: .infinity).frame(height: 112).background(.white.opacity(0.9), in: RoundedRectangle(cornerRadius: 18))
            .shadow(color: TapTraceTheme.ink.opacity(0.07), radius: 16, y: 8)
    }
    private func evidenceRow(_ symbol: String, _ title: String, _ detail: String, _ color: Color, _ connects: Bool) -> some View {
        HStack(spacing: 14) {
            VStack(spacing: 0) { Image(systemName: symbol).font(.title3).foregroundStyle(.white).frame(width: 46, height: 46).background(color.gradient, in: Circle()); if connects { Rectangle().fill(TapTraceTheme.border).frame(width: 2, height: 25) } }
            VStack(alignment: .leading, spacing: 3) { Text(title).font(.headline).foregroundStyle(TapTraceTheme.ink); Text(detail).font(.caption).foregroundStyle(TapTraceTheme.muted) }; Spacer()
        }
    }
}

