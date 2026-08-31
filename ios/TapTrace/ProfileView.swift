import SwiftUI
import UIKit

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
        }.navigationBarTitleDisplayMode(.inline).task { if case .idle = model.state { await model.load(address: address) } }
    }
}

struct LoadingProfileView: View {
    let stage: Int; let elapsedSeconds: Int
    @State private var pulse = false
    private let stages = [("location.magnifyingglass", "Confirming your address"), ("building.2", "Finding your water provider"), ("drop.triangle", "Translating the water report"), ("pipe.and.drop", "Checking pipe records"), ("checklist", "Building your action plan")]
    var body: some View {
        ZStack {
            TapTraceTheme.pageBackground.ignoresSafeArea()
            Circle().fill(TapTraceTheme.cyan.opacity(0.14)).frame(width: 270).blur(radius: 22).scaleEffect(pulse ? 1.15 : 0.85)
            VStack(spacing: 20) {
                Spacer(); BrandView(compact: true)
                ZStack {
                    Circle().stroke(TapTraceTheme.cyan.opacity(0.2), lineWidth: 18).frame(width: 154, height: 154).scaleEffect(pulse ? 1.12 : 0.92)
                    Image(systemName: stages[min(stage, 4)].0).font(.system(size: 48, weight: .semibold)).foregroundStyle(TapTraceTheme.gradient)
                }
                Text("FOLLOWING YOUR WATER").font(.caption2.bold()).tracking(1.3).foregroundStyle(Color("BrandBlue"))
                Text(stages[min(stage, 4)].1).font(.title.bold()).multilineTextAlignment(.center).foregroundStyle(TapTraceTheme.ink)
                ProgressView(value: Double(stage + 1), total: 5).tint(TapTraceTheme.cyan).padding(.horizontal, 30)
                Text(elapsedSeconds < 45 ? "Usually ready in under a minute" : "The free service is waking up—your request is still active.")
                    .font(.subheadline).multilineTextAlignment(.center).foregroundStyle(TapTraceTheme.muted)
                Spacer()
            }.padding(24)
        }.onAppear { withAnimation(.easeInOut(duration: 1.6).repeatForever(autoreverses: true)) { pulse = true } }
    }
}

struct ErrorProfileView: View {
    let address: String; let message: String; let retry: () -> Void
    var body: some View {
        VStack(spacing: 18) {
            Spacer(); Image(systemName: "wifi.exclamationmark").font(.system(size: 40)).foregroundStyle(.orange).frame(width: 82, height: 82).background(.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 24))
            Text("WE COULDN’T REACH THE WATER DATA").font(.caption2.bold()).tracking(1).foregroundStyle(Color("BrandBlue"))
            Text("Your address is saved.\nLet’s try that again.").font(.title.bold()).multilineTextAlignment(.center).foregroundStyle(TapTraceTheme.ink)
            Text("The secure data connection did not finish. This is a connection issue—not a statement about your water.").font(.subheadline).multilineTextAlignment(.center).foregroundStyle(TapTraceTheme.muted)
            Label(address, systemImage: "mappin.and.ellipse").font(.caption).padding().frame(maxWidth: .infinity, alignment: .leading).background(.white, in: RoundedRectangle(cornerRadius: 15))
            Button("Try again", systemImage: "arrow.clockwise", action: retry).buttonStyle(PrimaryButtonStyle())
            DisclosureGroup("Technical details") { Text(message).font(.caption2).foregroundStyle(.secondary).padding(.top, 6) }.font(.caption)
            Spacer()
        }.padding(24).background(TapTraceTheme.pageBackground.ignoresSafeArea())
    }
}

struct ProfileView: View {
    let address: String; let profile: WaterProfile
    @State private var insight: QualityInsight?
    @State private var path: ActionPath?
    @State private var appeared = false
    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 20) {
                hero
                scopeDiagram
                qualityStory
                pipesStory
                actionStory
                sources
            }.padding(.horizontal, 18).padding(.bottom, 34)
        }
        .background(TapTraceTheme.pageBackground.ignoresSafeArea()).navigationTitle("Your water plan")
        .sheet(item: $insight) { InsightSheet(insight: $0) }
        .sheet(item: $path) { RoadmapSheet(path: $0, profile: profile, address: address) }
        .onAppear { withAnimation(.smooth(duration: 0.7)) { appeared = true } }
    }

    private var hero: some View {
        VStack(alignment: .leading, spacing: 15) {
            HStack { Label(profile.providerName, systemImage: "building.2.fill").font(.caption.weight(.semibold)).lineLimit(1); Spacer(); Text("\(Int(profile.profileConfidence?.score ?? 0))% data confidence").font(.caption2.bold()).padding(.horizontal, 10).padding(.vertical, 6).background(.white.opacity(0.18), in: Capsule()) }
            HStack(alignment: .center, spacing: 14) {
                Image(systemName: headlineSymbol).font(.system(size: 34, weight: .bold)).frame(width: 70, height: 70).background(.white.opacity(0.2), in: Circle())
                VStack(alignment: .leading, spacing: 5) { Text("THE SIMPLE VERSION").font(.caption2.bold()).tracking(1.1); Text(headline).font(.title2.bold()); Text(headlineDetail).font(.subheadline).opacity(0.9) }
            }
            Label(profile.resolution?.matchedAddress ?? address, systemImage: "mappin.and.ellipse").font(.caption).opacity(0.88)
        }.foregroundStyle(.white).padding(20).background(TapTraceTheme.gradient, in: RoundedRectangle(cornerRadius: 26)).shadow(color: Color("BrandBlue").opacity(0.22), radius: 22, y: 12).padding(.top, 10)
            .offset(y: appeared ? 0 : 16).opacity(appeared ? 1 : 0)
    }
    private var headlineSymbol: String { profile.waterSystem?.currentViolationFlag == true ? "exclamationmark.triangle.fill" : profile.hasAboveBenchmark ? "exclamationmark.circle.fill" : "checkmark.shield.fill" }
    private var headline: String { profile.waterSystem?.currentViolationFlag == true ? "A provider notice needs your attention." : profile.hasAboveBenchmark ? "One or more reported results need a closer look." : "No current federal violation flag was found." }
    private var headlineDetail: String { "That does not prove what is at your faucet. TapTrace shows the strongest next step below." }

    private var scopeDiagram: some View {
        storyCard {
            sectionTitle("What this profile can tell you", "Three different layers—not one mystery score.")
            HStack(spacing: 6) {
                scopeNode("building.2.fill", "System", "Measured", .blue); connector
                scopeNode("pipe.and.drop.fill", "Pipes", profile.hasPropertyPipeRecord ? "On file" : "Limited", .cyan); connector
                scopeNode("house.fill", "Your tap", "Test needed", .indigo)
            }
        }
    }
    private var connector: some View { Image(systemName: "chevron.right").font(.caption.bold()).foregroundStyle(TapTraceTheme.border) }
    private func scopeNode(_ icon: String, _ title: String, _ status: String, _ color: Color) -> some View {
        VStack(spacing: 7) { Image(systemName: icon).font(.title2).foregroundStyle(color); Text(title).font(.caption.bold()); Text(status).font(.caption2).foregroundStyle(TapTraceTheme.muted) }.frame(maxWidth: .infinity).padding(.vertical, 12).background(color.opacity(0.08), in: RoundedRectangle(cornerRadius: 16))
    }

    private var qualityStory: some View {
        storyCard {
            sectionTitle("Your water report, translated", "Tap a topic to see what it means, possible health concerns, and how to reduce exposure.")
            if profile.qualityInsights.isEmpty { friendlyEmpty("No detailed report is translated yet", "We still found your provider and built an action plan.") }
            else { LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) { ForEach(profile.qualityInsights) { item in Button { insight = item } label: { insightCard(item) }.buttonStyle(.plain) } } }
            Text("These are provider-level results—not a sample from this home.").font(.caption).foregroundStyle(TapTraceTheme.muted)
        }
    }
    private func insightCard(_ item: QualityInsight) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack { Image(systemName: item.symbol).font(.title2).foregroundStyle(item.color); Spacer(); Image(systemName: "chevron.right").font(.caption.bold()).foregroundStyle(.secondary) }
            Text(item.title).font(.subheadline.bold()).foregroundStyle(TapTraceTheme.ink).multilineTextAlignment(.leading)
            Label(item.statusText, systemImage: item.statusSymbol).font(.caption2.weight(.semibold)).foregroundStyle(item.statusColor).lineLimit(2)
        }.padding(14).frame(maxWidth: .infinity, minHeight: 132, alignment: .leading).background(item.color.opacity(0.075), in: RoundedRectangle(cornerRadius: 18)).overlay(RoundedRectangle(cornerRadius: 18).stroke(item.color.opacity(0.16)))
    }

    private var pipesStory: some View {
        storyCard {
            sectionTitle("The pipes to your home", profile.hasPropertyPipeRecord ? "An official property-level record was found." : "Your exact service-line material is not confirmed in the available record.")
            HStack(spacing: 0) {
                pipeStop("water.waves", "Water main", "Utility network", .blue)
                pipeLine
                pipeStop("pipe.and.drop.fill", "Service line", profile.hasPropertyPipeRecord ? "Record found" : "Not confirmed", profile.hasPropertyPipeRecord ? .green : .orange)
                pipeLine
                pipeStop("house.fill", "Your home", "Private plumbing", .indigo)
            }.padding(.vertical, 8)
            if let context = profile.infrastructure?.assessment?.systemContext, let total = context.totalReported, total > 0 {
                VStack(alignment: .leading, spacing: 8) {
                    Text("The wider system—not your house").font(.caption.bold())
                    GeometryReader { geo in
                        HStack(spacing: 2) {
                            Rectangle().fill(.orange).frame(width: geo.size.width * CGFloat(Double((context.lead ?? 0) + (context.galvanizedRequiringReplacement ?? 0)) / Double(total)))
                            Rectangle().fill(.gray.opacity(0.35)).frame(width: geo.size.width * CGFloat(Double(context.notYetClassified ?? 0) / Double(total)))
                            Rectangle().fill(.green.opacity(0.65))
                        }.clipShape(Capsule())
                    }.frame(height: 12)
                    HStack { Label("Lead/galvanized", systemImage: "circle.fill").foregroundStyle(.orange); Spacer(); Label("Not classified", systemImage: "circle.fill").foregroundStyle(.gray); Spacer(); Label("Non-lead", systemImage: "circle.fill").foregroundStyle(.green) }.font(.caption2)
                }.padding(14).background(TapTraceTheme.surface, in: RoundedRectangle(cornerRadius: 16))
            }
            Button { path = .certainty } label: { Label(profile.hasPropertyPipeRecord ? "Understand my pipe record" : "Find out what my pipe is", systemImage: "magnifyingglass") }.buttonStyle(.borderedProminent).controlSize(.large).frame(maxWidth: .infinity)
        }
    }
    private var pipeLine: some View { Rectangle().fill(TapTraceTheme.border).frame(height: 3).frame(maxWidth: 32) }
    private func pipeStop(_ symbol: String, _ title: String, _ detail: String, _ color: Color) -> some View { VStack(spacing: 7) { Image(systemName: symbol).font(.title2).foregroundStyle(.white).frame(width: 48, height: 48).background(color.gradient, in: Circle()); Text(title).font(.caption.bold()); Text(detail).font(.caption2).foregroundStyle(TapTraceTheme.muted).multilineTextAlignment(.center).lineLimit(2) }.frame(maxWidth: .infinity) }

    private var actionStory: some View {
        storyCard {
            sectionTitle("Your best next move", "Start with one direction. You can explore another whenever you want.")
            Button { path = profile.bestPath } label: {
                HStack(spacing: 15) { Image(systemName: profile.bestPath.symbol).font(.title).foregroundStyle(.white).frame(width: 58, height: 58).background(.white.opacity(0.18), in: Circle()); VStack(alignment: .leading, spacing: 4) { Text("RECOMMENDED FOR YOU").font(.caption2.bold()).tracking(0.8); Text(profile.bestPath.title).font(.title3.bold()); Text(profile.bestPath.subtitle).font(.caption).opacity(0.9) }; Spacer(); Image(systemName: "arrow.right.circle.fill").font(.title2) }.foregroundStyle(.white).padding(18).background(TapTraceTheme.gradient, in: RoundedRectangle(cornerRadius: 22))
            }.buttonStyle(.plain)
            Text("Or choose your goal").font(.caption.bold()).foregroundStyle(TapTraceTheme.muted).padding(.top, 4)
            ForEach(ActionPath.allCases) { option in Button { path = option } label: { HStack(spacing: 13) { Image(systemName: option.symbol).foregroundStyle(option.color).frame(width: 42, height: 42).background(option.color.opacity(0.1), in: RoundedRectangle(cornerRadius: 12)); VStack(alignment: .leading, spacing: 3) { Text(option.title).font(.subheadline.bold()).foregroundStyle(TapTraceTheme.ink); Text(option.subtitle).font(.caption).foregroundStyle(TapTraceTheme.muted) }; Spacer(); Image(systemName: "chevron.right").foregroundStyle(.secondary) }.padding(12).background(TapTraceTheme.surface, in: RoundedRectangle(cornerRadius: 16)) }.buttonStyle(.plain) }
        }
    }

    private var sources: some View {
        VStack(alignment: .leading, spacing: 10) { Text("Official sources").font(.headline); if let raw = profile.providerResources?.validatedReportURL, let url = URL(string: raw) { Link("Open the provider’s full water report", destination: url) }; if let raw = profile.providerResources?.officialFacilityRecord, let url = URL(string: raw) { Link("Open the EPA facility record", destination: url) }; Text("TapTrace explains public records. It does not replace a certified test of water from your faucet.").font(.caption2).foregroundStyle(.secondary) }.padding(.horizontal, 4)
    }

    private func storyCard<Content: View>(@ViewBuilder content: () -> Content) -> some View { VStack(alignment: .leading, spacing: 16, content: content).padding(18).background(.white.opacity(0.92), in: RoundedRectangle(cornerRadius: 24)).overlay(RoundedRectangle(cornerRadius: 24).stroke(TapTraceTheme.border.opacity(0.55))).shadow(color: TapTraceTheme.ink.opacity(0.055), radius: 16, y: 8) }
    private func sectionTitle(_ title: String, _ detail: String) -> some View { VStack(alignment: .leading, spacing: 6) { Text(title).font(.title2.bold()).foregroundStyle(TapTraceTheme.ink); Text(detail).font(.subheadline).foregroundStyle(TapTraceTheme.muted) } }
    private func friendlyEmpty(_ title: String, _ detail: String) -> some View { HStack(spacing: 12) { Image(systemName: "doc.text.magnifyingglass").font(.title2).foregroundStyle(Color("BrandBlue")); VStack(alignment: .leading) { Text(title).font(.headline); Text(detail).font(.caption).foregroundStyle(.secondary) } }.padding().background(TapTraceTheme.surface, in: RoundedRectangle(cornerRadius: 16)) }
}

struct QualityInsight: Identifiable {
    let id: String; let title: String; let symbol: String; let color: Color; let plainMeaning: String; let healthContext: String; let prevention: String; let sourceURL: URL; let measurements: [Measurement]
    var needsAttention: Bool { measurements.contains { ($0.benchmarkComparison ?? "").contains("above") } }
    var statusText: String { needsAttention ? "Needs a closer look" : measurements.allSatisfy { $0.benchmarkComparison != nil && !($0.benchmarkComparison ?? "").contains("not_applicable") } ? "Reported at or below benchmark" : "Monitored or detected" }
    var statusSymbol: String { needsAttention ? "exclamationmark.triangle.fill" : "checkmark.circle.fill" }
    var statusColor: Color { needsAttention ? .orange : .green }
}

extension WaterProfile {
    var hasAboveBenchmark: Bool { allMeasurements.contains { ($0.benchmarkComparison ?? "").contains("above") } }
    var hasPropertyPipeRecord: Bool { infrastructure?.evidenceLevel == "official_property_record" || infrastructure?.officialStatus != nil }
    var bestPath: ActionPath { if waterSystem?.currentViolationFlag == true || hasAboveBenchmark { return .protect }; if !hasPropertyPipeRecord { return .certainty }; return .protect }
    var qualityInsights: [QualityInsight] {
        (waterQuality?.sections ?? []).compactMap { section in
            let items = section.measurements ?? []; guard !items.isEmpty, let category = section.category else { return nil }
            let meta = InsightMeta.forCategory(category)
            return QualityInsight(id: category, title: meta.title, symbol: meta.symbol, color: meta.color, plainMeaning: meta.meaning, healthContext: meta.health, prevention: meta.prevention, sourceURL: meta.url, measurements: items)
        }.sorted { $0.needsAttention && !$1.needsAttention }
    }
}

private struct InsightMeta {
    let title: String; let symbol: String; let color: Color; let meaning: String; let health: String; let prevention: String; let url: URL
    static func forCategory(_ value: String) -> InsightMeta {
        let epa = URL(string: "https://www.epa.gov/ground-water-and-drinking-water")!
        if value.contains("lead") { return .init(title: "Lead & pipe metals", symbol: "brain.head.profile.fill", color: .orange, meaning: "Lead and copper can enter water from service lines or household plumbing.", health: "Lead matters most for babies, children, and pregnancy because it can affect brain and nervous-system development.", prevention: "Use cold water for drinking, flush stagnant water, consider a filter certified for lead reduction, and test at the tap for a home-specific answer.", url: URL(string: "https://www.epa.gov/ground-water-and-drinking-water/basic-information-about-lead-drinking-water")!) }
        if value.contains("pfas") || value.contains("unregulated") { return .init(title: "PFAS & emerging chemicals", symbol: "shield.lefthalf.filled", color: .purple, meaning: "These chemicals are monitored because they can persist for a long time in people and the environment.", health: "Long-term exposure to certain PFAS has been associated with immune, developmental, cholesterol, liver, and some cancer effects.", prevention: "Check whether the reported chemical was detected, use a certified PFAS-reduction filter if appropriate, and follow provider updates.", url: URL(string: "https://www.epa.gov/pfas/pfas-explained")!) }
        if value.contains("disinfection") { return .init(title: "Treatment byproducts", symbol: "sparkles", color: .teal, meaning: "Disinfectants protect against germs, but they can form byproducts when they react with natural material in water.", health: "Standards balance the urgent benefit of killing germs with possible risks from long-term exposure to high byproduct levels.", prevention: "Review the reported benchmark; carbon filtration may reduce some byproducts when maintained correctly.", url: epa) }
        if value.contains("nitrate") { return .init(title: "Nitrates", symbol: "leaf.fill", color: .green, meaning: "Nitrate can enter water from fertilizers, wastewater, and natural sources.", health: "High nitrate is especially dangerous for infants because it can reduce the blood’s ability to carry oxygen.", prevention: "If a result is elevated, follow official guidance and use an appropriate alternate water source; boiling does not remove nitrate.", url: URL(string: "https://www.epa.gov/ground-water-and-drinking-water/national-primary-drinking-water-regulations")!) }
        if value.contains("microbial") { return .init(title: "Germs & bacteria", symbol: "allergens.fill", color: .red, meaning: "Microbial tests look for organisms that can signal contamination.", health: "Contaminated water can cause stomach illness and can be more serious for vulnerable people.", prevention: "Follow boil-water or provider notices immediately; ordinary filters are not substitutes for official emergency instructions.", url: epa) }
        if value.contains("aesthetic") { return .init(title: "Hardness & minerals", symbol: "drop.degreesign.fill", color: .cyan, meaning: "These affect taste, scale, and appliance buildup more often than health.", health: "Hardness itself is generally an aesthetic or household-maintenance concern rather than a federal health violation.", prevention: "Treatment is optional for taste or scale; choose equipment for the specific mineral issue.", url: epa) }
        if value.contains("federal") { return .init(title: "Federal compliance", symbol: "checkmark.seal.fill", color: .blue, meaning: "This is the EPA’s reported compliance status for the public water system.", health: "A violation flag means the provider’s notice deserves review; no flag does not prove every faucet is contaminant-free.", prevention: "Read provider notices and test your tap when you need a home-specific result.", url: URL(string: "https://echo.epa.gov/")!) }
        return .init(title: "Other monitored substances", symbol: "testtube.2", color: .indigo, meaning: "The provider report includes additional substances monitored at the system level.", health: "Health meaning depends on the substance, amount, benchmark, and duration of exposure.", prevention: "Open the result details and source report before choosing any treatment.", url: epa)
    }
}

struct InsightSheet: View {
    let insight: QualityInsight; @Environment(\.dismiss) private var dismiss
    var body: some View { NavigationStack { ScrollView { VStack(alignment: .leading, spacing: 18) {
        HStack { Image(systemName: insight.symbol).font(.system(size: 34)).foregroundStyle(insight.color).frame(width: 72, height: 72).background(insight.color.opacity(0.1), in: RoundedRectangle(cornerRadius: 22)); VStack(alignment: .leading) { Text(insight.title).font(.title2.bold()); Label(insight.statusText, systemImage: insight.statusSymbol).font(.caption.bold()).foregroundStyle(insight.statusColor) } }
        explainBlock("What it means", "eye.fill", insight.plainMeaning, .blue)
        explainBlock("Why people care", "heart.text.square.fill", insight.healthContext, .orange)
        explainBlock("How to reduce exposure", "shield.checkered", insight.prevention, .green)
        VStack(alignment: .leading, spacing: 10) { Text("What the report says").font(.headline); ForEach(Array(insight.measurements.prefix(6).enumerated()), id: \.offset) { _, item in HStack { VStack(alignment: .leading) { Text(item.name ?? "Measurement").font(.subheadline.bold()); Text(item.benchmarkType ?? "System-level result").font(.caption).foregroundStyle(.secondary) }; Spacer(); Text(item.result ?? "Reported").font(.caption.bold()).multilineTextAlignment(.trailing) }.padding(.vertical, 5) } }.padding().background(TapTraceTheme.surface, in: RoundedRectangle(cornerRadius: 18))
        Link("Read the official health information", destination: insight.sourceURL).buttonStyle(.borderedProminent)
        Text("This provider-level report does not measure water from this home’s faucet.").font(.caption).foregroundStyle(.secondary)
    }.padding(20) } .navigationTitle("Plain-language guide").navigationBarTitleDisplayMode(.inline).toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } } } }
    private func explainBlock(_ title: String, _ icon: String, _ text: String, _ color: Color) -> some View { HStack(alignment: .top, spacing: 13) { Image(systemName: icon).foregroundStyle(color).frame(width: 36, height: 36).background(color.opacity(0.1), in: RoundedRectangle(cornerRadius: 10)); VStack(alignment: .leading, spacing: 5) { Text(title).font(.headline); Text(text).font(.subheadline).foregroundStyle(TapTraceTheme.muted) } } }
}

enum ActionPath: String, CaseIterable, Identifiable {
    case protect, certainty, officialHelp
    var id: Self { self }
    var title: String { switch self { case .protect: "Protect my household now"; case .certainty: "Get a confirmed answer"; case .officialHelp: "Ask for official help" } }
    var subtitle: String { switch self { case .protect: "Low-cost steps and the right filter"; case .certainty: "Tap testing and pipe verification"; case .officialHelp: "A ready-to-send request or complaint" } }
    var symbol: String { switch self { case .protect: "shield.fill"; case .certainty: "checkmark.seal.fill"; case .officialHelp: "envelope.badge.fill" } }
    var color: Color { switch self { case .protect: .green; case .certainty: .blue; case .officialHelp: .orange } }
}

struct RoadmapSheet: View {
    let path: ActionPath; let profile: WaterProfile; let address: String
    @Environment(\.dismiss) private var dismiss
    var steps: [(String, String, String)] { switch path {
        case .protect: [("1", "Use cold water", "Use cold tap water for drinking and cooking; hot water can dissolve plumbing metals more readily."), ("2", "Flush after water sits", "Run cold water before use when it has been sitting for several hours."), ("3", "Choose certification—not marketing", "Match a third-party-certified filter to the specific concern shown in your profile."), ("4", "Replace cartridges on time", "An overdue cartridge may not provide the claimed reduction.")]
        case .certainty: [("1", "Start with a certified tap test", "A home sample answers what public system data cannot: what reaches this faucet."), ("2", "Ask for your service-line record", "Give the utility your address and request both public- and private-side material."), ("3", "Verify if the record is missing", "Use the utility-approved inspection or plumber-confirmed process."), ("4", "Update your plan", "Choose treatment or replacement based on the confirmed result.")]
        case .officialHelp: [("1", "Copy the prepared message", "TapTrace fills in your address, provider, and the exact records to request."), ("2", "Send it to your utility", "Use the provider’s contact page, customer-service email, or service-line program."), ("3", "Save the response", "Keep the case number, reply, and any test or inspection result."), ("4", "Escalate if needed", "If the issue is unresolved, contact your state drinking-water program or EPA regional office.")]
    } }
    var body: some View { NavigationStack { ScrollView { VStack(alignment: .leading, spacing: 18) {
        HStack(spacing: 14) { Image(systemName: path.symbol).font(.title).foregroundStyle(.white).frame(width: 64, height: 64).background(path.color.gradient, in: RoundedRectangle(cornerRadius: 20)); VStack(alignment: .leading) { Text("YOUR ROADMAP").font(.caption2.bold()).tracking(1).foregroundStyle(path.color); Text(path.title).font(.title2.bold()) } }
        Text("Start here").font(.headline); Text(steps[0].1).font(.title.bold()).foregroundStyle(TapTraceTheme.ink); Text(steps[0].2).font(.subheadline).foregroundStyle(TapTraceTheme.muted)
        VStack(spacing: 0) { ForEach(Array(steps.enumerated()), id: \.offset) { index, step in HStack(alignment: .top, spacing: 13) { VStack(spacing: 0) { Text(step.0).font(.caption.bold()).foregroundStyle(.white).frame(width: 34, height: 34).background(index == 0 ? path.color : TapTraceTheme.muted, in: Circle()); if index < steps.count - 1 { Rectangle().fill(TapTraceTheme.border).frame(width: 2, height: 54) } }; VStack(alignment: .leading, spacing: 4) { Text(step.1).font(.headline); Text(step.2).font(.caption).foregroundStyle(TapTraceTheme.muted) }; Spacer() } } }.padding().background(TapTraceTheme.surface, in: RoundedRectangle(cornerRadius: 20))
        if path == .protect {
            NavigationLink {
                FilterRecommendationView(profile: profile)
            } label: {
                Label("Find a filter matched to my profile", systemImage: "waterbottle.fill")
            }
            .buttonStyle(PrimaryButtonStyle())
        }
        if path == .certainty { Link("Find a state-certified drinking-water lab", destination: URL(string: "https://www.epa.gov/dwlabcert/contact-information-certification-programs-and-certified-laboratories-drinking-water")!).buttonStyle(.borderedProminent) }
        if path == .officialHelp { ContactTemplateView(profile: profile, address: address) }
    }.padding(20) }.navigationTitle("Action plan").navigationBarTitleDisplayMode(.inline).toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } } } }
}

struct FilterRecommendationView: View {
    let profile: WaterProfile
    private let productURL = URL(string: "https://www.brita.com/products/brita-tahoe-water-pitcher-elite-filter/")!
    private let productImageURL = URL(string: "https://images.ctfassets.net/bugnyha6so6z/4HWQmPEsI5IFPCoJr620vP/49db2d517cef5f7c2adbe74933aa122f/PDP_hero_-_tahoe_white_-_elite-_desktop_1x.webp")!
    private let nsfURL = URL(string: "https://info.nsf.org/Certified/dwtu/listings.asp?CompanyName=brita")!

    private var needsLeadReduction: Bool {
        profile.allMeasurements.contains { ($0.name ?? "").localizedCaseInsensitiveContains("lead") } || !profile.hasPropertyPipeRecord
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("MATCHED TO YOUR PROFILE").font(.caption2.bold()).tracking(1.2).foregroundStyle(Color("BrandBlue"))
                    Text("A filter for the concerns shown in your report").font(.largeTitle.bold()).foregroundStyle(TapTraceTheme.ink)
                    Text("TapTrace matches certifications to concerns—not products to popularity.").font(.subheadline).foregroundStyle(TapTraceTheme.muted)
                }

                HStack(spacing: 10) {
                    matchPill("Pb", needsLeadReduction ? "Lead reduction" : "Metal reduction")
                    matchPill("••", "Class I particles")
                }

                VStack(alignment: .leading, spacing: 16) {
                    AsyncImage(url: productImageURL) { phase in
                        switch phase {
                        case let .success(image): image.resizable().scaledToFit()
                        case .failure: Image(systemName: "waterbottle.fill").resizable().scaledToFit().padding(55).foregroundStyle(TapTraceTheme.cyan)
                        default: ProgressView().frame(maxWidth: .infinity, minHeight: 220)
                        }
                    }
                    .frame(maxWidth: .infinity, minHeight: 220, maxHeight: 280)
                    .background(.white, in: RoundedRectangle(cornerRadius: 20))

                    Label("Matches your profile", systemImage: "checkmark.seal.fill")
                        .font(.caption.bold()).foregroundStyle(Color("BrandBlue"))
                    Text("Brita Tahoe Pitcher + Elite Filter").font(.title2.bold()).foregroundStyle(TapTraceTheme.ink)
                    Text("10-cup pitcher · approximately 6-month filter life").font(.subheadline).foregroundStyle(TapTraceTheme.muted)
                    Text("$41.99").font(.title.bold()).foregroundStyle(Color("BrandBlue"))

                    VStack(alignment: .leading, spacing: 9) {
                        Label("Certified for lead reduction", systemImage: "checkmark.circle.fill")
                        Label("Certified for Particulate Class I", systemImage: "checkmark.circle.fill")
                    }.font(.subheadline.weight(.semibold)).foregroundStyle(TapTraceTheme.ink)

                    Link(destination: productURL) {
                        Label("View product at Brita", systemImage: "arrow.up.right.square")
                    }.buttonStyle(PrimaryButtonStyle())
                }
                .padding(18).background(.white, in: RoundedRectangle(cornerRadius: 24))
                .overlay(RoundedRectangle(cornerRadius: 24).stroke(TapTraceTheme.border.opacity(0.7)))
                .shadow(color: TapTraceTheme.ink.opacity(0.08), radius: 18, y: 9)

                Link("Verify this product in NSF’s official directory", destination: nsfURL)
                    .font(.subheadline.weight(.semibold))
                Text("Prices and availability can change. Confirm the exact contaminant-reduction claim before buying. A filter reduces selected contaminants; it does not verify your pipe material or replace a certified tap test.")
                    .font(.caption).foregroundStyle(TapTraceTheme.muted)
            }.padding(20)
        }
        .background(TapTraceTheme.pageBackground.ignoresSafeArea())
        .navigationTitle("Filter match").navigationBarTitleDisplayMode(.inline)
    }

    private func matchPill(_ badge: String, _ text: String) -> some View {
        HStack(spacing: 8) {
            Text(badge).font(.caption.bold()).foregroundStyle(Color("BrandBlue"))
                .frame(width: 30, height: 30).background(Color("BrandBlue").opacity(0.1), in: Circle())
            Text(text).font(.caption.weight(.semibold)).foregroundStyle(TapTraceTheme.ink)
        }.padding(.horizontal, 11).padding(.vertical, 8).background(.white, in: Capsule())
            .overlay(Capsule().stroke(TapTraceTheme.border.opacity(0.7)))
    }
}

struct ContactTemplateView: View {
    let profile: WaterProfile; let address: String
    @State private var copied = false
    var message: String { """
    Subject: Request for water-quality and service-line information

    Hello \(profile.providerName),

    I am requesting the latest available records for \(address):
    • The public- and private-side service-line material and verification method
    • The latest Consumer Confidence Report and any current public notices
    • Information about certified tap testing or service-line inspection programs

    Public water system ID: \(profile.waterSystem?.pwsid ?? profile.providerResources?.pwsid ?? "not listed")

    Please explain any record that is missing or not yet confirmed and tell me the next step for obtaining a verified answer.

    Thank you.
    """ }
    var body: some View { VStack(alignment: .leading, spacing: 12) {
        Text("Ready-to-send request").font(.title3.bold()); Text("Review it, copy it, then submit it through your utility’s contact page or customer-service email.").font(.subheadline).foregroundStyle(TapTraceTheme.muted)
        ScrollView { Text(message).font(.caption).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }.frame(height: 230).padding(12).background(.white, in: RoundedRectangle(cornerRadius: 14)).overlay(RoundedRectangle(cornerRadius: 14).stroke(TapTraceTheme.border))
        HStack { Button(copied ? "Copied" : "Copy message", systemImage: copied ? "checkmark" : "doc.on.doc") { UIPasteboard.general.string = message; copied = true }.buttonStyle(.borderedProminent); ShareLink(item: message) { Label("Share", systemImage: "square.and.arrow.up") }.buttonStyle(.bordered) }
        if let raw = profile.providerResources?.officialFacilityRecord, let url = URL(string: raw) { Link("Open this provider’s EPA record", destination: url) }
        Link("Find your state drinking-water contact", destination: URL(string: "https://www.epa.gov/dwreginfo/drinking-water-regulations-and-contaminants")!)
        Text("TapTrace prepares the message but never sends it without you reviewing and submitting it.").font(.caption2).foregroundStyle(.secondary)
    }.padding().background(.orange.opacity(0.07), in: RoundedRectangle(cornerRadius: 20)) }
}
