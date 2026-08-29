import Foundation

enum APIError: LocalizedError {
    case invalidConfiguration, invalidResponse, server(Int, String?), decoding
    var errorDescription: String? {
        switch self {
        case .invalidConfiguration: "TapTrace is missing its API configuration."
        case .invalidResponse: "The water-data service returned an invalid response."
        case let .server(code, detail): detail ?? "The water-data service returned error \(code)."
        case .decoding: "TapTrace received water data in an unexpected format."
        }
    }
}

struct APIClient: Sendable {
    private let session: URLSession
    private let baseURL: URL

    init(session: URLSession = .shared) throws {
        guard let raw = Bundle.main.object(forInfoDictionaryKey: "TapTraceAPIBaseURL") as? String,
              let url = URL(string: raw) else { throw APIError.invalidConfiguration }
        self.session = session; self.baseURL = url
    }

    func profile(for address: String) async throws -> WaterProfile {
        let url = baseURL.appendingPathComponent("water-profile")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 120
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["address": address])
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard (200..<300).contains(http.statusCode) else {
            let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String
            throw APIError.server(http.statusCode, detail)
        }
        do { return try JSONDecoder().decode(WaterProfile.self, from: data) }
        catch { throw APIError.decoding }
    }
}

@MainActor
@Observable
final class ProfileViewModel {
    enum State { case idle, loading, loaded(WaterProfile), failed(String) }
    var state: State = .idle
    var elapsedSeconds = 0
    var loadingStage = 0

    func load(address: String) async {
        state = .loading
        elapsedSeconds = 0
        loadingStage = 0
        let clock = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(1))
                guard !Task.isCancelled, let self else { return }
                elapsedSeconds += 1
                loadingStage = min(4, elapsedSeconds / 10)
            }
        }
        defer { clock.cancel() }

        do {
            let client = try APIClient()
            do {
                state = .loaded(try await client.profile(for: address))
            } catch let error as URLError where [.timedOut, .networkConnectionLost, .cannotConnectToHost].contains(error.code) {
                loadingStage = 4
                try await Task.sleep(for: .seconds(3))
                state = .loaded(try await client.profile(for: address))
            }
        } catch is CancellationError {
            state = .idle
        } catch {
            state = .failed(error.localizedDescription)
        }
    }
}
