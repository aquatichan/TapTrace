import SwiftUI
import UIKit

private enum PremiumLinks {
    static let lead = URL(string: "https://www.epa.gov/ground-water-and-drinking-water/basic-information-about-lead-drinking-water")!
    static let filter = URL(string: "https://www.brita.com/products/brita-tahoe-water-pitcher-elite-filter/")!
    static let alternatives = URL(string: "https://info.nsf.org/Certified/dwtu/")!
}

struct PremiumPlateImage: View {
    let name: String
    var body: some View {
        GeometryReader { proxy in
            Image(name).resizable().scaledToFill()
                .frame(width: proxy.size.width, height: proxy.size.height).clipped()
                .accessibilityHidden(true)
        }
        .background(Color.white).ignoresSafeArea()
    }
}

struct ClearHit: View {
    let label: String
    let action: () -> Void
    var body: some View {
        Button(action: action) { Color.clear.contentShape(Rectangle()) }
            .buttonStyle(.plain).accessibilityLabel(label)
    }
}

struct ProfileContainerView: View {
    let address: String
    @Bindable var model: ProfileViewModel
    var body: some View {
        Group {
            switch model.state {
            case .idle, .loading:
                PremiumLoadingView(stage: model.loadingStage, elapsedSeconds: model.elapsedSeconds)
            case let .loaded(profile):
                PremiumProfileView(address: address, profile: profile)
            case let .failed(message):
                PremiumErrorView(message: message) { Task { await model.load(address: address) } }
            }
        }
        .toolbar(.hidden, for: .navigationBar)
        .task { if case .idle = model.state { await model.load(address: address) } }
    }
}

struct PremiumLoadingView: View {
    let stage: Int
    let elapsedSeconds: Int
    @State private var pulse = false
    var body: some View {
        ZStack {
            PremiumPlateImage(name: "LoadingPremium")
            Circle().stroke(Color.cyan.opacity(0.22), lineWidth: 5)
                .frame(width: 118, height: 118).scaleEffect(pulse ? 1.12 : 0.88)
        }
        .onAppear { withAnimation(.easeInOut(duration: 1.25).repeatForever(autoreverses: true)) { pulse = true } }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Building your water profile. Step \(min(stage + 1, 5)) of 5. \(elapsedSeconds) seconds elapsed.")
    }
}

struct PremiumErrorView: View {
    let message: String
    let retry: () -> Void
    var body: some View {
        ZStack {
            PremiumPlateImage(name: "ErrorPremium")
            VStack { Spacer(); ClearHit(label: "Try again", action: retry).frame(height: 92); Spacer().frame(height: 210) }
        }
        .accessibilityHint(message)
    }
}

struct PremiumProfileView: View {
    let address: String
    let profile: WaterProfile
    var body: some View {
        ZStack {
            PremiumPlateImage(name: "ProfilePremium")
            GeometryReader { proxy in
                ZStack {
                    NavigationLink(destination: PremiumQualityView(profile: profile)) { Color.clear }
                        .frame(width: proxy.size.width * 0.84, height: proxy.size.height * 0.13)
                        .position(x: proxy.size.width / 2, y: proxy.size.height * 0.44)
                        .accessibilityLabel("Open water quality details")
                    NavigationLink(destination: PremiumPipesView(profile: profile)) { Color.clear }
                        .frame(width: proxy.size.width * 0.84, height: proxy.size.height * 0.11)
                        .position(x: proxy.size.width / 2, y: proxy.size.height * 0.58)
                        .accessibilityLabel("Open pipe details")
                    NavigationLink(destination: PremiumRoadmapView(profile: profile)) { Color.clear }
                        .frame(width: proxy.size.width * 0.84, height: proxy.size.height * 0.13)
                        .position(x: proxy.size.width / 2, y: proxy.size.height * 0.75)
                        .accessibilityLabel("Start my action plan")
                    NavigationLink(destination: PremiumActionsView(profile: profile)) { Color.clear }
                        .frame(width: proxy.size.width * 0.84, height: proxy.size.height * 0.11)
                        .position(x: proxy.size.width / 2, y: proxy.size.height * 0.91)
                        .accessibilityLabel("See all action paths")
                }
            }
        }
    }
}

private struct PremiumBackPlate<Content: View>: View {
    let image: String
    @ViewBuilder let content: () -> Content
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        ZStack {
            PremiumPlateImage(name: image)
            GeometryReader { _ in
                ZStack {
                    ClearHit(label: "Back") { dismiss() }.frame(width: 80, height: 70).position(x: 45, y: 42)
                    content()
                }
            }
        }
        .toolbar(.hidden, for: .navigationBar)
    }
}

struct PremiumQualityView: View {
    let profile: WaterProfile
    var body: some View {
        PremiumBackPlate(image: "QualityPremium") {
            GeometryReader { proxy in
                ZStack {
                    NavigationLink(destination: PremiumLeadView(profile: profile)) { Color.clear }
                        .frame(width: proxy.size.width * 0.88, height: proxy.size.height * 0.17)
                        .position(x: proxy.size.width / 2, y: proxy.size.height * 0.47)
                        .accessibilityLabel("Learn about lead")
                    NavigationLink(destination: PremiumActionsView(profile: profile)) { Color.clear }
                        .frame(width: proxy.size.width * 0.88, height: 100)
                        .position(x: proxy.size.width / 2, y: proxy.size.height * 0.88)
                        .accessibilityLabel("See what I can do at home")
                }
            }
        }
    }
}

struct PremiumLeadView: View {
    let profile: WaterProfile
    var body: some View {
        PremiumBackPlate(image: "LeadPremium") {
            GeometryReader { proxy in
                ZStack {
                    NavigationLink(destination: PremiumRoadmapView(profile: profile)) { Color.clear }
                        .frame(width: proxy.size.width * 0.86, height: 90)
                        .position(x: proxy.size.width / 2, y: proxy.size.height * 0.82)
                    Link(destination: PremiumLinks.lead) { Color.clear }
                        .frame(width: proxy.size.width * 0.86, height: 72)
                        .position(x: proxy.size.width / 2, y: proxy.size.height * 0.91)
                        .accessibilityLabel("Read EPA lead guidance")
                }
            }
        }
    }
}

struct PremiumPipesView: View {
    let profile: WaterProfile
    var body: some View {
        PremiumBackPlate(image: "PipesPremium") {
            GeometryReader { proxy in
                ZStack {
                    NavigationLink(destination: PremiumRoadmapView(profile: profile)) { Color.clear }
                        .frame(width: proxy.size.width * 0.86, height: 90)
                        .position(x: proxy.size.width / 2, y: proxy.size.height * 0.78)
                    NavigationLink(destination: PremiumContactView(profile: profile)) { Color.clear }
                        .frame(width: proxy.size.width * 0.86, height: 82)
                        .position(x: proxy.size.width / 2, y: proxy.size.height * 0.89)
                }
            }
        }
    }
}

struct PremiumActionsView: View {
    let profile: WaterProfile
    var body: some View {
        PremiumBackPlate(image: "ActionsPremium") {
            GeometryReader { proxy in
                ZStack {
                    NavigationLink(destination: PremiumRoadmapView(profile: profile)) { Color.clear }
                        .frame(width: proxy.size.width * 0.88, height: 145).position(x: proxy.size.width / 2, y: proxy.size.height * 0.43)
                    NavigationLink(destination: PremiumPipesView(profile: profile)) { Color.clear }
                        .frame(width: proxy.size.width * 0.88, height: 145).position(x: proxy.size.width / 2, y: proxy.size.height * 0.61)
                    NavigationLink(destination: PremiumContactView(profile: profile)) { Color.clear }
                        .frame(width: proxy.size.width * 0.88, height: 145).position(x: proxy.size.width / 2, y: proxy.size.height * 0.79)
                }
            }
        }
    }
}

struct PremiumRoadmapView: View {
    let profile: WaterProfile
    @State private var completed = false
    var body: some View {
        PremiumBackPlate(image: "RoadmapPremium") {
            GeometryReader { proxy in
                ZStack {
                    NavigationLink(destination: PremiumFilterView()) { Color.clear }
                        .frame(width: proxy.size.width * 0.86, height: 92)
                        .position(x: proxy.size.width / 2, y: proxy.size.height * 0.70)
                        .accessibilityLabel("Find the right certified filter")
                    ClearHit(label: completed ? "Step one completed" : "Mark step one done") { completed.toggle() }
                        .frame(width: proxy.size.width * 0.86, height: 92)
                        .position(x: proxy.size.width / 2, y: proxy.size.height * 0.85)
                    if completed {
                        Image(systemName: "checkmark.circle.fill").font(.system(size: 34)).foregroundStyle(.green)
                            .position(x: proxy.size.width * 0.84, y: proxy.size.height * 0.85)
                    }
                }
            }
        }
    }
}

struct PremiumFilterView: View {
    var body: some View {
        PremiumBackPlate(image: "FilterPremium") {
            GeometryReader { proxy in
                ZStack {
                    Link(destination: PremiumLinks.filter) { Color.clear }
                        .frame(width: proxy.size.width * 0.86, height: 96)
                        .position(x: proxy.size.width / 2, y: proxy.size.height * 0.79)
                        .accessibilityLabel("View Brita Tahoe pitcher with Elite lead-reduction filter")
                    Link(destination: PremiumLinks.alternatives) { Color.clear }
                        .frame(width: proxy.size.width * 0.86, height: 76)
                        .position(x: proxy.size.width / 2, y: proxy.size.height * 0.90)
                        .accessibilityLabel("See other NSF certified filter matches")
                }
            }
        }
    }
}

struct PremiumContactView: View {
    let profile: WaterProfile
    @State private var copied = false
    @Environment(\.openURL) private var openURL
    private var message: String {
        "Hello \(profile.providerName), I am requesting the available service-line material and water-quality records for my residence. Please tell me whether the utility and customer sides are recorded, how the material was verified, and where I can review the latest Consumer Confidence Report. Thank you."
    }
    var body: some View {
        PremiumBackPlate(image: "ContactPremium") {
            GeometryReader { proxy in
                ZStack {
                    ClearHit(label: "Copy request and open email") {
                        UIPasteboard.general.string = message
                        copied = true
                        let encoded = message.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ""
                        if let url = URL(string: "mailto:?subject=Water%20record%20request&body=\(encoded)") { openURL(url) }
                    }
                    .frame(width: proxy.size.width * 0.86, height: 96)
                    .position(x: proxy.size.width / 2, y: proxy.size.height * 0.81)
                    if copied {
                        Text("Copied").font(.caption.bold()).padding(8).background(.green, in: Capsule()).foregroundStyle(.white)
                            .position(x: proxy.size.width * 0.82, y: proxy.size.height * 0.72)
                    }
                }
            }
        }
    }
}
