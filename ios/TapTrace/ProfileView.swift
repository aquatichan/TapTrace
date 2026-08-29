import SwiftUI

struct ProfileContainerView: View {
    let address: String
    @Bindable var model: ProfileViewModel
    var body: some View {
        Group {
            switch model.state {
            case .idle, .loading: LoadingProfileView(stage: model.loadingStage, elapsedSeconds: model.elapsedSeconds)
            case let .loaded(profile): ProfileView(address: address, profile: profile)
            case let .failed(message): ErrorProfileView(address: address, message: message) { Task { await model.load(address: address) } }
            }
        }
        .navigationBarTitleDisplayMode(.inline)
        .task { if case .idle = model.state { await model.load(address: address) } }
    }
}

struct LoadingProfileView: View {
    let stage: Int
    let elapsedSeconds: Int
    private let stages = [
        ("location.magnifyingglass", "Confirming your address"),
        ("building.2", "Finding your water provider"),
        ("drop.triangle", "Reviewing available measurements"),
        ("pipe.and.drop", "Checking infrastructure records"),
        ("checklist", "Preparing your recommendations")
    ]

    var body: some View {
        VStack(spacing: 18) {
            Spacer(minLength: 12)
            BrandView(compact: true)
            Image("WaterRoute").resizable().scaledToFit().frame(maxHeight: 250).accessibilityHidden(true)
            Text("BUILDING YOUR PROFILE").font(.caption.weight(.bold)).tracking(1.4).foregroundStyle(Color("BrandBlue"))
            Text("Following your water\nfrom source to tap")
                .font(.system(.title, design: .rounded, weight: .bold))
                .multilineTextAlignment(.center).foregroundStyle(TapTraceTheme.ink)

            VStack(spacing: 12) {
                ForEach(Array(stages.enumerated()), id: \.offset) { index, item in
                    HStack(spacing: 12) {
                        Image(systemName: index < stage ? "checkmark.circle.fill" : item.0)
                            .font(.body.weight(.semibold))
                            .foregroundStyle(index <= stage ? Color("BrandBlue") : TapTraceTheme.border)
                            .frame(width: 24)
                        Text(item.1).font(.subheadline.weight(index == stage ? .semibold : .regular))
                            .foregroundStyle(index <= stage ? TapTraceTheme.ink : TapTraceTheme.muted)
                        Spacer()
                        if index == stage { ProgressView().controlSize(.small).tint(Color("BrandBlue")) }
                    }
                }
            }
            .padding(18)
            .background(Color.white, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18).stroke(TapTraceTheme.border.opacity(0.8)))

            VStack(spacing: 5) {
                Text(estimatedWaitText).font(.subheadline.weight(.semibold)).foregroundStyle(TapTraceTheme.ink)
                Text(elapsedSeconds < 45 ? "Official systems may take a moment to respond." : "The free data service is waking up. Your profile is still processing.")
                    .font(.caption).multilineTextAlignment(.center).foregroundStyle(TapTraceTheme.muted)
            }
            Spacer(minLength: 12)
        }
        .padding(.horizontal, 24).padding(.vertical, 12)
        .background(TapTraceTheme.pageBackground.ignoresSafeArea())
        .preferredColorScheme(.light)
    }

    private var estimatedWaitText: String {
        if elapsedSeconds < 15 { return "Estimated wait: under 1 minute" }
        if elapsedSeconds < 60 { return "About \(max(10, 70 - elapsedSeconds)) seconds remaining" }
        return "Almost there — keeping your request active"
    }
}

struct ErrorProfileView: View {
    let address: String; let message: String; let retry: () -> Void
    var body: some View {
        VStack(spacing: 16) {
            Spacer(); Image(systemName: "exclamationmark.triangle").font(.largeTitle).foregroundStyle(.orange).frame(width: 70, height: 70).background(.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 20))
            Text("PROFILE NOT AVAILABLE YET").font(.caption2.bold()).tracking(1).foregroundStyle(Color("BrandBlue"))
            Text("We couldn’t complete this water profile.").font(.title.bold()).multilineTextAlignment(.center).foregroundStyle(TapTraceTheme.ink)
            Text(message).font(.subheadline).multilineTextAlignment(.center).foregroundStyle(TapTraceTheme.muted)
            Label(address, systemImage: "mappin.and.ellipse").font(.caption).padding().frame(maxWidth: .infinity, alignment: .leading).background(.background, in: RoundedRectangle(cornerRadius: 13))
            Button("Try again", systemImage: "arrow.clockwise", action: retry).buttonStyle(PrimaryButtonStyle())
            Text("This does not mean the address has unsafe water. It means TapTrace could not retrieve enough data to build the profile right now.").font(.caption).multilineTextAlignment(.center).foregroundStyle(.secondary)
            Spacer()
        }.padding(24).background(TapTraceTheme.surface.ignoresSafeArea())
    }
}

enum ProfileSection: String, CaseIterable, Identifiable { case overview = "Overview", quality = "Quality", pipes = "Pipes", actions = "Actions"; var id: Self { self } }

struct ProfileView: View {
    let address: String; let profile: WaterProfile
    @State private var section: ProfileSection = .overview
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack(alignment: .bottom) {
                    VStack(alignment: .leading, spacing: 7) { Text(profile.providerName.uppercased()).font(.caption2.bold()).tracking(1).foregroundStyle(Color("BrandBlue")); Text("Your water profile").font(.largeTitle.bold()).foregroundStyle(TapTraceTheme.ink); Label(profile.resolution?.matchedAddress ?? address, systemImage: "mappin.and.ellipse").font(.caption).foregroundStyle(TapTraceTheme.muted) }
                    Spacer(); ConfidenceGauge(confidence: profile.profileConfidence)
                }
                Picker("Profile section", selection: $section) { ForEach(ProfileSection.allCases) { Text($0.rawValue).tag($0) } }.pickerStyle(.segmented)
                switch section { case .overview: OverviewSection(profile: profile, section: $section); case .quality: QualitySection(profile: profile); case .pipes: PipesSection(profile: profile); case .actions: ActionsSection(profile: profile) }
                Text(profile.safety?.summary ?? "TapTrace summarizes public records and system-level monitoring. It is not a laboratory test of water from this faucet.").font(.caption2).foregroundStyle(.secondary).padding(.vertical, 8)
            }.padding(20)
        }.background(Color(.systemBackground)).navigationTitle("Your water profile")
    }
}

struct ConfidenceGauge: View {
    let confidence: Confidence?
    var score: Double { min(max(confidence?.score ?? 0, 0), 100) }
    var body: some View { ZStack { Circle().stroke(Color(.systemGray5), lineWidth: 7); Circle().trim(from: 0, to: score / 100).stroke(TapTraceTheme.cyan, style: StrokeStyle(lineWidth: 7, lineCap: .round)).rotationEffect(.degrees(-90)); VStack(spacing: 0) { Text(score, format: .number.precision(.fractionLength(0))).font(.headline.bold()); Text(confidence?.label ?? "Limited").font(.caption2).foregroundStyle(.secondary) } }.frame(width: 68, height: 68).accessibilityElement(children: .ignore).accessibilityLabel("Profile confidence \(Int(score)) out of 100, \(confidence?.label ?? "Limited")") }
}

struct OverviewSection: View {
    let profile: WaterProfile; @Binding var section: ProfileSection
    var body: some View { VStack(spacing: 14) {
        if profile.waterSystem?.currentViolationFlag == true { callout("exclamationmark.triangle", "Provider notice needs review", "A current federal compliance flag appears in available system records.", .orange) }
        card("Water quality", action: { section = .quality }) { HStack { Text("\(profile.allMeasurements.count)").font(.largeTitle.bold()).foregroundStyle(Color("BrandBlue")); VStack(alignment: .leading) { Text("available measurements").font(.subheadline.bold()); Text("System-level, not a sample from this home.").font(.caption).foregroundStyle(.secondary) }; Spacer() } }
        card("Infrastructure", action: { section = .pipes }) { HStack { Image(systemName: "pipe.and.drop").font(.title2).foregroundStyle(Color("BrandBlue")); VStack(alignment: .leading) { Text(profile.infrastructure?.officialStatus ?? profile.infrastructure?.displayStatus ?? "Assessment available").font(.subheadline.bold()); Text("Confidence describes evidence strength, not lead probability.").font(.caption).foregroundStyle(.secondary) }; Spacer() } }
        card("Recommended next steps", action: { section = .actions }) { VStack(alignment: .leading, spacing: 10) { ForEach(Array((profile.recommendedActions ?? []).prefix(2).enumerated()), id: \.offset) { index, item in Label(item.title ?? "Review your profile", systemImage: "\(index + 1).circle.fill").font(.subheadline) } } }
    } }
}

struct QualitySection: View {
    let profile: WaterProfile
    var body: some View { VStack(alignment: .leading, spacing: 14) { sectionHeader("Reported water measurements", "These describe the resolved public water system—not water measured at this faucet."); if profile.allMeasurements.isEmpty { empty("No normalized measurements yet", "TapTrace still provides federal system records, provider details, and next steps when a local report is unavailable.") } else { ForEach(Array(profile.allMeasurements.enumerated()), id: \.offset) { _, item in HStack { VStack(alignment: .leading) { Text(item.name ?? "Measurement").font(.subheadline.bold()); Text(item.benchmarkType ?? "System-level measurement").font(.caption).foregroundStyle(.secondary) }; Spacer(); Text(item.result ?? item.unit.map { "Reported (\($0))" } ?? "Reported").font(.subheadline.bold()) }.padding(.vertical, 8); Divider() } }; callout("info.circle", "System-level evidence", "Missing measurements never mean a contaminant is absent. Tap testing is the only way to answer what is in this home’s water.", Color("BrandBlue")) } }
}

struct PipesSection: View {
    let profile: WaterProfile
    var body: some View { VStack(alignment: .leading, spacing: 14) { sectionHeader("What brings water to this home", profile.infrastructure?.evidenceLevel == "official_property_record" ? "An official property record was found for this address." : "Available records may not establish this home’s pipe material."); HStack(spacing: 16) { Image(systemName: "pipe.and.drop.fill").font(.largeTitle).foregroundStyle(Color("BrandBlue")); VStack(alignment: .leading) { Text("Current status").font(.caption).foregroundStyle(.secondary); Text(profile.infrastructure?.officialStatus ?? profile.infrastructure?.displayStatus ?? "Assessment available").font(.headline); Text("Utility side: \(profile.infrastructure?.utilitySide ?? "Not established")\nCustomer side: \(profile.infrastructure?.customerSide ?? "Not established")").font(.caption).foregroundStyle(.secondary) } }.padding().frame(maxWidth: .infinity, alignment: .leading).background(TapTraceTheme.surface, in: RoundedRectangle(cornerRadius: 16)); callout("checkmark.shield", "\(Int(profile.infrastructure?.confidence?.score ?? 0)) \(profile.infrastructure?.confidence?.label ?? "Limited") confidence", "This score describes the strength of available infrastructure evidence. It is not the probability that this home has lead pipes.", .orange) } }
}

struct ActionsSection: View {
    let profile: WaterProfile; @Environment(\.openURL) private var openURL
    var body: some View { VStack(alignment: .leading, spacing: 14) { sectionHeader("What you can do next", "Prioritized from the evidence available for this address."); if (profile.recommendedActions ?? []).isEmpty { empty("No tailored actions available yet", "Contact the resolved water provider and ask for its latest consumer report and service-line inventory.") } else { ForEach(Array((profile.recommendedActions ?? []).enumerated()), id: \.offset) { index, action in Button { if let raw = action.url, let url = URL(string: raw) { openURL(url) } } label: { HStack(alignment: .top) { Image(systemName: "\(index + 1).circle.fill").foregroundStyle(Color("BrandBlue")); VStack(alignment: .leading, spacing: 5) { Text(action.title ?? "Review your profile").font(.subheadline.bold()).foregroundStyle(TapTraceTheme.ink); Text(action.text ?? action.reason ?? "").font(.caption).foregroundStyle(.secondary) }; Spacer(); Image(systemName: "chevron.right").foregroundStyle(.secondary) }.padding().background(.background, in: RoundedRectangle(cornerRadius: 15)).overlay(RoundedRectangle(cornerRadius: 15).stroke(Color(.separator).opacity(0.5))) }.buttonStyle(.plain).disabled(action.url == nil) } } } }
}

private func sectionHeader(_ title: String, _ detail: String) -> some View { VStack(alignment: .leading, spacing: 7) { Text(title).font(.title2.bold()).foregroundStyle(TapTraceTheme.ink); Text(detail).font(.subheadline).foregroundStyle(TapTraceTheme.muted) } }
private func callout(_ symbol: String, _ title: String, _ detail: String, _ color: Color) -> some View { HStack(alignment: .top, spacing: 12) { Image(systemName: symbol).foregroundStyle(color); VStack(alignment: .leading, spacing: 5) { Text(title).font(.subheadline.bold()); Text(detail).font(.caption).foregroundStyle(.secondary) } }.padding().frame(maxWidth: .infinity, alignment: .leading).background(color.opacity(0.09), in: RoundedRectangle(cornerRadius: 14)) }
private func empty(_ title: String, _ detail: String) -> some View { VStack(spacing: 8) { Image(systemName: "info.circle").font(.title2).foregroundStyle(Color("BrandBlue")); Text(title).font(.headline); Text(detail).font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center) }.padding(24).frame(maxWidth: .infinity).background(TapTraceTheme.surface, in: RoundedRectangle(cornerRadius: 15)) }
private func card<Content: View>(_ title: String, action: @escaping () -> Void, @ViewBuilder content: () -> Content) -> some View { VStack(alignment: .leading, spacing: 13) { HStack { Text(title).font(.headline); Spacer(); Button("See details", action: action).font(.caption.bold()) }; content() }.padding().background(.background, in: RoundedRectangle(cornerRadius: 16)).overlay(RoundedRectangle(cornerRadius: 16).stroke(Color(.separator).opacity(0.45))) }
