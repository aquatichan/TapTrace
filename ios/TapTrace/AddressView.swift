import SwiftUI
@preconcurrency import MapKit
import CoreLocation

@MainActor
final class AddressSearchModel: NSObject, ObservableObject, MKLocalSearchCompleterDelegate {
    @Published private(set) var suggestions: [MKLocalSearchCompletion] = []
    private let completer = MKLocalSearchCompleter()
    private var queryTask: Task<Void, Never>?

    override init() {
        super.init()
        completer.delegate = self
        completer.resultTypes = [.address]
    }

    func update(_ query: String) {
        queryTask?.cancel()
        let value = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard value.count >= 4 else { suggestions = []; return }
        queryTask = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(250))
            guard !Task.isCancelled else { return }
            self?.completer.queryFragment = value
        }
    }

    func clear() { queryTask?.cancel(); suggestions = [] }

    func resolvedAddress(for completion: MKLocalSearchCompletion) async -> String? {
        let request = MKLocalSearch.Request(completion: completion)
        request.resultTypes = [.address]
        guard let item = try? await MKLocalSearch(request: request).start().mapItems.first else { return nil }
        var place = item.placemark
        if place.postalCode?.isEmpty != false, let location = place.location,
           let reverse = try? await CLGeocoder().reverseGeocodeLocation(location).first {
            place = MKPlacemark(placemark: reverse)
        }
        let street = [place.subThoroughfare, place.thoroughfare]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }.joined(separator: " ")
        let city = place.locality?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let state = place.administrativeArea?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let zip = place.postalCode?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !street.isEmpty, !city.isEmpty, state.count == 2, zip.count >= 5 else { return nil }
        return "\(street), \(city), \(state) \(zip)"
    }

    func completerDidUpdateResults(_ completer: MKLocalSearchCompleter) {
        suggestions = Array(completer.results.prefix(4))
    }

    func completer(_ completer: MKLocalSearchCompleter, didFailWithError error: Error) {
        suggestions = []
    }
}

struct AddressView: View {
    @State private var address = ""
    @State private var showProfile = false
    @State private var showAbout = false
    @State private var validationMessage: String?
    @State private var model = ProfileViewModel()
    @State private var selectedSuggestion = false
    @State private var canonicalAddress: String?
    @State private var resolvingSuggestion = false
    @StateObject private var search = AddressSearchModel()
    @FocusState private var addressFocused: Bool

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    header
                    heroCopy
                    Image("WaterRoute")
                        .resizable().scaledToFit().frame(maxWidth: .infinity)
                        .padding(.horizontal, -18).padding(.top, 10)
                        .accessibilityHidden(true)
                    journeySteps.padding(.top, 4)
                    addressForm.padding(.top, 26)
                }
                .padding(.horizontal, 24).padding(.top, 8).padding(.bottom, 28)
            }
            .scrollDismissesKeyboard(.interactively)
            .background(TapTraceTheme.pageBackground.ignoresSafeArea())
            .navigationDestination(isPresented: $showProfile) { ProfileContainerView(address: address, model: model) }
            .sheet(isPresented: $showAbout) { AboutView().preferredColorScheme(.light) }
        }
        .preferredColorScheme(.light)
    }

    private var header: some View {
        HStack(spacing: 10) {
            BrandView()
            Spacer(minLength: 8)
            Button { showAbout = true } label: {
                HStack(spacing: 5) { Text("Why TapTrace?"); Image(systemName: "chevron.right") }
                    .font(.subheadline.weight(.semibold)).foregroundStyle(Color("BrandBlue"))
            }
        }
    }

    private var heroCopy: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Trace your water\nfrom source to tap.")
                .font(.system(.largeTitle, design: .rounded, weight: .bold))
                .foregroundStyle(TapTraceTheme.ink).lineSpacing(1)
            Text("Enter your address to discover your water’s journey and what’s in it.")
                .font(.body).foregroundStyle(TapTraceTheme.muted)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.top, 38)
    }

    private var addressForm: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Enter your address").font(.headline).foregroundStyle(TapTraceTheme.ink).padding(.bottom, 10)
            HStack(spacing: 12) {
                Image(systemName: "mappin.and.ellipse").font(.title3).foregroundStyle(TapTraceTheme.muted)
                TextField("Street, city, state ZIP", text: $address)
                    .textContentType(.fullStreetAddress).textInputAutocapitalization(.words).submitLabel(.go)
                    .focused($addressFocused).onSubmit(startProfile)
                    .onChange(of: address) { _, value in
                        if selectedSuggestion { selectedSuggestion = false } else {
                            canonicalAddress = nil
                            search.update(value)
                        }
                        validationMessage = nil
                    }
            }
            .padding(.horizontal, 16).frame(minHeight: 58)
            .background(Color.white, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay { RoundedRectangle(cornerRadius: 14).stroke(validationMessage == nil ? TapTraceTheme.border : .red, lineWidth: 1) }

            if addressFocused && !search.suggestions.isEmpty {
                VStack(spacing: 0) {
                    ForEach(Array(search.suggestions.enumerated()), id: \.offset) { index, item in
                        Button {
                            selectedSuggestion = true
                            address = [item.title, item.subtitle].filter { !$0.isEmpty }.joined(separator: ", ")
                            search.clear(); addressFocused = false
                            resolvingSuggestion = true
                            Task {
                                let resolved = await search.resolvedAddress(for: item)
                                if let resolved {
                                    selectedSuggestion = true
                                    address = resolved
                                    canonicalAddress = resolved
                                }
                                resolvingSuggestion = false
                            }
                        } label: {
                            HStack(alignment: .top, spacing: 11) {
                                Image(systemName: "mappin").foregroundStyle(Color("BrandBlue")).padding(.top, 2)
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(item.title).font(.subheadline.weight(.semibold)).foregroundStyle(TapTraceTheme.ink)
                                    if !item.subtitle.isEmpty { Text(item.subtitle).font(.caption).foregroundStyle(TapTraceTheme.muted) }
                                }
                                Spacer()
                            }
                            .padding(.horizontal, 14).padding(.vertical, 11)
                        }
                        .buttonStyle(.plain)
                        if index < search.suggestions.count - 1 { Divider().padding(.leading, 42) }
                    }
                }
                .background(Color.white, in: RoundedRectangle(cornerRadius: 14))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(TapTraceTheme.border))
                .shadow(color: TapTraceTheme.ink.opacity(0.08), radius: 14, y: 7)
                .padding(.top, 7)
            }

            if let validationMessage { Text(validationMessage).font(.caption).foregroundStyle(.red).padding(.top, 7) }
            Button(action: startProfile) { Label("Start my profile", systemImage: "magnifyingglass") }
                .buttonStyle(PrimaryButtonStyle()).padding(.top, 14)
                .disabled(resolvingSuggestion)
                .opacity(resolvingSuggestion ? 0.72 : 1)
            Label("Results combine official provider records, federal monitoring, and available infrastructure data.", systemImage: "checkmark.shield")
                .font(.caption).foregroundStyle(TapTraceTheme.muted)
                .fixedSize(horizontal: false, vertical: true).padding(.top, 18)
        }
    }

    private var journeySteps: some View {
        HStack(spacing: 6) {
            step("mappin.circle.fill", "Address", "Where you live", true); line(true)
            step("drop.circle", "Profile", "Water insights", false); line(false)
            step("checklist", "Actions", "What you can do", false)
        }
        .frame(maxWidth: .infinity)
    }

    private func step(_ symbol: String, _ title: String, _ subtitle: String, _ active: Bool) -> some View {
        VStack(spacing: 5) {
            Image(systemName: symbol).font(.title2)
            Text(title).font(.caption.weight(.bold))
            Text(subtitle).font(.caption2).lineLimit(1).minimumScaleFactor(0.78)
        }
        .foregroundStyle(active ? Color("BrandBlue") : TapTraceTheme.muted)
        .frame(maxWidth: .infinity)
    }

    private func line(_ active: Bool) -> some View {
        Rectangle().fill(active ? Color("BrandBlue") : TapTraceTheme.border).frame(height: 1).frame(maxWidth: 46)
    }

    private func startProfile() {
        guard !resolvingSuggestion else {
            validationMessage = "Finishing your address…"
            return
        }
        let trimmed = (canonicalAddress ?? address).trimmingCharacters(in: .whitespacesAndNewlines)
        guard isCompleteAddress(trimmed) else {
            validationMessage = "Choose a complete address including city, state, and ZIP code."
            addressFocused = true; search.update(trimmed); return
        }
        address = trimmed; validationMessage = nil; addressFocused = false; search.clear()
        model = ProfileViewModel(); showProfile = true
    }

    private func isCompleteAddress(_ value: String) -> Bool {
        let hasStreetNumber = value.range(of: #"\d+\s+\S+"#, options: .regularExpression) != nil
        let hasState = value.range(of: #"(?:,|\s)\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?$"#, options: [.regularExpression, .caseInsensitive]) != nil
        return value.count >= 14 && hasStreetNumber && hasState
    }
}

struct AboutView: View {
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    Image("LogoMark").resizable().scaledToFit().frame(width: 116, height: 116).padding(.top, 34)
                    Text("CLEAR ANSWERS, HONEST LIMITS").font(.caption.weight(.bold)).tracking(1.5).foregroundStyle(Color("BrandBlue"))
                    Text("Understand your water without false certainty.")
                        .font(.system(.largeTitle, design: .rounded, weight: .bold))
                        .multilineTextAlignment(.center).foregroundStyle(TapTraceTheme.ink)
                    Text("TapTrace connects an address to official provider, monitoring, and infrastructure records—then explains what the evidence does and does not establish.")
                        .font(.body).multilineTextAlignment(.center).foregroundStyle(TapTraceTheme.muted)
                }
                .padding(.horizontal, 28).padding(.bottom, 40)
            }
            .background(TapTraceTheme.pageBackground.ignoresSafeArea())
            .navigationTitle("Why TapTrace?").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() }.fontWeight(.semibold) } }
        }
    }
}

