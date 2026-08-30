import SwiftUI

struct OnboardingView: View {
    @Binding var isComplete: Bool
    @State private var page = 0

    var body: some View {
        GeometryReader { proxy in
            ZStack {
                Color.white.ignoresSafeArea()
                Image(page == 0 ? "OnboardOne" : "OnboardTwo")
                    .resizable()
                    .scaledToFill()
                    .frame(width: proxy.size.width, height: proxy.size.height)
                    .clipped()
                    .accessibilityHidden(true)

                VStack {
                    HStack {
                        if page == 1 {
                            Button { withAnimation(.easeInOut(duration: 0.3)) { page = 0 } } label: {
                                Image(systemName: "chevron.left")
                                    .font(.title2.bold())
                                    .frame(width: 56, height: 56)
                                    .contentShape(Rectangle())
                            }
                            .accessibilityLabel("Back")
                        }
                        Spacer()
                        if page == 0 {
                            Button("Skip") { isComplete = true }
                                .font(.title3)
                                .foregroundStyle(TapTraceTheme.ink)
                                .padding(18)
                        }
                    }
                    Spacer()
                    Button {
                        if page == 0 {
                            withAnimation(.easeInOut(duration: 0.35)) { page = 1 }
                        } else {
                            isComplete = true
                        }
                    } label: {
                        Color.clear
                            .frame(height: 78)
                            .contentShape(RoundedRectangle(cornerRadius: 18))
                    }
                    .accessibilityLabel(page == 0 ? "Show me how" : "Enter my address")
                    .padding(.horizontal, 38)
                    .padding(.bottom, 40)
                }
            }
        }
        .ignoresSafeArea()
        .preferredColorScheme(.light)
    }
}
