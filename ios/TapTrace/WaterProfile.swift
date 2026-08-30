import Foundation

struct WaterProfile: Decodable, Sendable {
    var resolution: Resolution?
    var waterSystem: WaterSystem?
    var infrastructure: Infrastructure?
    var profileConfidence: Confidence?
    var waterQuality: WaterQuality?
    var recommendedActions: [RecommendedAction]?
    var safety: Safety?
    var providerResources: ProviderResources?

    enum CodingKeys: String, CodingKey {
        case resolution, infrastructure, safety
        case waterSystem = "water_system"
        case profileConfidence = "profile_confidence"
        case waterQuality = "water_quality"
        case recommendedActions = "recommended_actions"
        case providerResources = "provider_resources"
    }
}

struct Resolution: Decodable, Sendable { var status: String?; var matchedAddress: String?; var waterSystemCandidates: [WaterSystemCandidate]?; enum CodingKeys: String, CodingKey { case status; case matchedAddress = "matched_address"; case waterSystemCandidates = "water_system_candidates" } }
struct WaterSystemCandidate: Decodable, Sendable { var name: String?; var pwsid: String? }
struct WaterSystem: Decodable, Sendable { var name: String?; var pwsid: String?; var currentViolationFlag: Bool?; var populationServed: Int?; enum CodingKeys: String, CodingKey { case name, pwsid; case currentViolationFlag = "current_violation_flag"; case populationServed = "population_served" } }
struct Confidence: Decodable, Sendable { var score: Double?; var label: String? }
struct Infrastructure: Decodable, Sendable {
    var displayStatus: String?; var officialStatus: String?; var utilitySide: String?; var customerSide: String?; var evidenceLevel: String?; var confidence: Confidence?; var assessment: InfrastructureAssessment?
    enum CodingKeys: String, CodingKey { case confidence, assessment; case displayStatus = "display_status"; case officialStatus = "official_status"; case utilitySide = "utility_side"; case customerSide = "customer_side"; case evidenceLevel = "evidence_level" }
}
struct InfrastructureAssessment: Decodable, Sendable { var systemContext: SystemContext?; enum CodingKeys: String, CodingKey { case systemContext = "system_context" } }
struct SystemContext: Decodable, Sendable {
    var lead: Int?; var galvanizedRequiringReplacement: Int?; var nonlead: Int?; var totalReported: Int?; var notYetClassified: Int?
    enum CodingKeys: String, CodingKey { case lead, nonlead; case galvanizedRequiringReplacement = "galvanized_requiring_replacement"; case totalReported = "total_reported"; case notYetClassified = "not_yet_classified" }
}
struct WaterQuality: Decodable, Sendable { var availability: String?; var report: WaterReport?; var sections: [WaterSection]? }
struct WaterReport: Decodable, Sendable { var reportYear: Int?; enum CodingKeys: String, CodingKey { case reportYear = "report_year" } }
struct WaterSection: Decodable, Sendable { var category: String?; var status: String?; var measurements: [Measurement]? }
struct Measurement: Decodable, Sendable { var name: String?; var result: String?; var unit: String?; var benchmarkComparison: String?; var benchmarkType: String?; var benchmarkValue: Double?; var dataYear: Int?; enum CodingKeys: String, CodingKey { case name, result, unit; case benchmarkComparison = "benchmark_comparison"; case benchmarkType = "benchmark_type"; case benchmarkValue = "benchmark_value"; case dataYear = "data_year" } }
struct RecommendedAction: Decodable, Sendable { var title: String?; var text: String?; var reason: String?; var url: String?; var priority: Int? }
struct Safety: Decodable, Sendable { var summary: String? }
struct ProviderResources: Decodable, Sendable {
    var pwsid: String?; var providerName: String?; var validatedReportURL: String?; var officialFacilityRecord: String?; var epaCCRSearch: String?; var contactInstruction: String?
    enum CodingKeys: String, CodingKey { case pwsid; case providerName = "provider_name"; case validatedReportURL = "validated_report_url"; case officialFacilityRecord = "official_facility_record"; case epaCCRSearch = "epa_ccr_search"; case contactInstruction = "contact_instruction" }
}

extension WaterProfile {
    var providerName: String { waterSystem?.name ?? resolution?.waterSystemCandidates?.first?.name ?? "Provider not resolved" }
    var allMeasurements: [Measurement] { waterQuality?.sections?.flatMap { $0.measurements ?? [] } ?? [] }
}
