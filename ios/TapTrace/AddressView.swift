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
            try? await Task.sleep(for: .milliseconds(220))
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

    func completerDidUpdateResults(_ completer: MKLocalSearchCompleter) { suggestions = Array(completer.results.prefix(3)) }
    func completer(_ completer: MKLocalSearchCompleter, didFailWithError error: Error) { suggestions = [] }
}

struct AddressView: View {
    @State private var address = ""
    @State private var canonicalAddress: String?
    @State private var showProfile = false
    @State private var model = ProfileViewModel()
    @State private var resolving = false
    @State private var validationMessage: String?
    @StateObject private var search = AddressSearchModel()
    @FocusState private var focused: Bool

    var body: some View {
        NavigationStack {
            GeometryReader { proxy in
                ZStack(alignment: .top) {
                    Color.white.ignoresSafeArea()
                    Image("AddressPremium")
                        .resizable().scaledToFill()
                        .frame(width: proxy.size.width, height: proxy.size.height)
                        .clipped().accessibilityHidden(true)

                    // The approved plate supplies the illustrated upper half. This live surface
                    // replaces its sample field with real MapKit search and validation.
                    VStack(spacing: 10) {
                        searchField
                        if focused && !search.suggestions.isEmpty { suggestionList }
                        if let validationMessage {
                            Text(validationMessage).font(.caption).foregroundStyle(.red)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        Button(action: startProfile) {
                            HStack(spacing: 14) {
                                Text(resolving ? "Finishing your address…" : "Use this address")
                                Image(systemName: "arrow.right")
                            }
                        }
                        .buttonStyle(PremiumButtonStyle())
                        .disabled(resolving)
                        Label("Your address is used only to find public water records.", systemImage: "lock.fill")
                            .font(.caption).foregroundStyle(TapTraceTheme.muted)
                    }
                    .padding(.horizontal, 22)
                    .padding(.top, 18)
                    .padding(.bottom, 28)
                    .frame(width: proxy.size.width, height: proxy.size.height * 0.48, alignment: .top)
                    .background(Color.white)
                    .position(x: proxy.size.width / 2, y: proxy.size.height * 0.76)
                }
            }
            .ignoresSafeArea()
            .navigationDestination(isPresented: $showProfile) {
                ProfileContainerView(address: canonicalAddress ?? address, model: model)
            }
        }
        .preferredColorScheme(.light)
    }

    private var searchField: some View {
        HStack(spacing: 12) {
            Image(systemName: "magnifyingglass").font(.title2).foregroundStyle(Color("BrandBlue"))
            TextField("Street, city, state ZIP", text: $address)
                .font(.body).textContentType(.fullStreetAddress).textInputAutocapitalization(.words)
                .submitLabel(.go).focused($focused).onSubmit(startProfile)
                .onChange(of: address) { _, value in canonicalAddress = nil; validationMessage = nil; search.update(value) }
            if !address.isEmpty { Button { address = ""; search.clear() } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary) } }
        }
        .padding(.horizontal, 18).frame(height: 58)
        .background(.white, in: RoundedRectangle(cornerRadius: 27))
        .overlay(RoundedRectangle(cornerRadius: 27).stroke(focused ? Color("BrandBlue") : TapTraceTheme.border, lineWidth: focused ? 2 : 1))
        .shadow(color: Color("BrandBlue").opacity(focused ? 0.17 : 0.06), radius: 10, y: 5)
    }

    private var suggestionList: some View {
        VStack(spacing: 0) {
            ForEach(Array(search.suggestions.enumerated()), id: \.offset) { index, item in
                Button { choose(item) } label: {
                    HStack(spacing: 12) {
                        Image(systemName: "mappin").font(.title3).foregroundStyle(Color("BrandBlue"))
                        VStack(alignment: .leading, spacing: 2) {
                            Text(item.title).font(.subheadline.weight(.semibold)).foregroundStyle(TapTraceTheme.ink).lineLimit(1)
                            if !item.subtitle.isEmpty { Text(item.subtitle).font(.caption).foregroundStyle(TapTraceTheme.muted).lineLimit(1) }
                        }
                        Spacer(); Image(systemName: "arrow.up.left").foregroundStyle(.secondary)
                    }.padding(.horizontal, 16).padding(.vertical, 10)
                }.buttonStyle(.plain)
                if index < search.suggestions.count - 1 { Divider().padding(.leading, 52) }
            }
        }
        .background(.white, in: RoundedRectangle(cornerRadius: 20))
        .overlay(RoundedRectangle(cornerRadius: 20).stroke(TapTraceTheme.border.opacity(0.7)))
        .shadow(color: TapTraceTheme.ink.opacity(0.08), radius: 12, y: 6)
    }

    private func choose(_ completion: MKLocalSearchCompletion) {
        address = [completion.title, completion.subtitle].filter { !$0.isEmpty }.joined(separator: ", ")
        search.clear(); focused = false; resolving = true
        Task {
            if let value = await search.resolvedAddress(for: completion) { address = value; canonicalAddress = value }
            resolving = false
        }
    }

    private func startProfile() {
        guard !resolving else { validationMessage = "Finishing your address…"; return }
        let value = (canonicalAddress ?? address).trimmingCharacters(in: .whitespacesAndNewlines)
        guard value.range(of: #"\d+\s+\S+"#, options: .regularExpression) != nil,
              value.range(of: #"(?:,|\s)\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?$"#, options: [.regularExpression, .caseInsensitive]) != nil else {
            validationMessage = "Choose a complete address including city, state, and ZIP code."
            focused = true; search.update(value); return
        }
        address = value; focused = false; search.clear(); model = ProfileViewModel(); showProfile = true
    }
}

struct PremiumButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.title3.bold()).foregroundStyle(.white)
            .frame(maxWidth: .infinity).frame(height: 62)
            .background(TapTraceTheme.gradient, in: RoundedRectangle(cornerRadius: 18))
            .shadow(color: Color("BrandBlue").opacity(0.2), radius: 12, y: 7)
            .scaleEffect(configuration.isPressed ? 0.985 : 1)
    }
}
