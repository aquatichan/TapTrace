import SwiftUI

enum TapTraceTheme {
    static let ink = Color(red: 0.04, green: 0.17, blue: 0.33)
    static let muted = Color(red: 0.33, green: 0.43, blue: 0.55)
    static let cyan = Color(red: 0.13, green: 0.81, blue: 0.89)
    static let surface = Color(red: 0.96, green: 0.98, blue: 1)
    static let pageBackground = LinearGradient(
        colors: [.white, Color(red: 0.955, green: 0.978, blue: 1)],
        startPoint: .top,
        endPoint: .bottom
    )
    static let border = Color(red: 0.78, green: 0.83, blue: 0.89)
    static let gradient = LinearGradient(
        colors: [Color("BrandBlue"), Color(red: 0.03, green: 0.60, blue: 0.90), cyan],
        startPoint: .leading,
        endPoint: .trailing
    )
}

struct BrandView: View {
    var compact = false
    var body: some View {
        HStack(spacing: 8) {
            Image("LogoMark").resizable().scaledToFit().frame(width: compact ? 38 : 46, height: compact ? 38 : 46)
            Text("TapTrace").font(compact ? .title3 : .title2).fontWeight(.bold).foregroundStyle(TapTraceTheme.ink)
        }
        .accessibilityElement(children: .ignore).accessibilityLabel("TapTrace")
    }
}

struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline).foregroundStyle(.white).frame(maxWidth: .infinity).frame(minHeight: 56)
            .background(TapTraceTheme.gradient, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .shadow(color: Color("BrandBlue").opacity(0.18), radius: 12, y: 7)
            .scaleEffect(configuration.isPressed ? 0.985 : 1)
    }
}
