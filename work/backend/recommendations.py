"""Deterministic, evidence-scoped recommendations for TapTrace profiles."""

from __future__ import annotations


RULESET_VERSION = "2026-08-27.1"
EPA_CERTIFIED_LABS = "https://www.epa.gov/dwlabcert/contact-information-certification-programs-and-certified-laboratories-drinking-water"
EPA_LEAD_FILTERS = "https://www.epa.gov/water-research/consumer-tool-identifying-point-use-and-pitcher-filters-certified-reduce-lead"
EPA_PFAS_FILTERS = "https://www.epa.gov/water-research/identifying-drinking-water-filters-certified-reduce-pfas"


def _action(priority: int, kind: str, title: str, text: str, *, reason: str,
            url: str | None = None) -> dict:
    result = {"priority": priority, "type": kind, "title": title, "text": text, "reason": reason,
              "ruleset_version": RULESET_VERSION}
    if url:
        result["url"] = url
    return result


def build_recommendations(resolved: dict, infrastructure: dict,
                          sections: list[dict]) -> list[dict]:
    """Return explainable actions; absence of data never creates reassurance."""
    actions: list[dict] = []
    boundary = resolved.get("selected_water_system_boundary") or {}
    federal = resolved.get("federal_water_system_profile") or {}
    ccr = resolved.get("consumer_confidence_report_profile") or {}
    report = ccr.get("report") or {}
    provider_url = boundary.get("detailed_facility_report") or federal.get("detailed_facility_report")
    epa_ccr_search = "https://ordspub.epa.gov/ords/safewater/f?p=136:102"
    well_context = resolved.get("private_well_context") or {}

    if not boundary:
        actions.append(_action(1, "identify_provider", "Find your water provider",
            "Check a recent water bill or contact your city or county water office. The address may use a private well or a service area that is not mapped yet.",
            reason="No single mapped public water system was confirmed for this address."))
        if well_context:
            actions.append(_action(1, "confirm_private_well", "Confirm whether this property uses a private well",
                "Ask the owner or check the water bill and well-completion record. If it uses a well, arrange routine testing through a state-certified laboratory.",
                reason=f"EPA estimates {well_context.get('estimated_well_use_percent_2010')}% well use in the surrounding 2010 Census block; this is area evidence, not property confirmation.",
                url=EPA_CERTIFIED_LABS))
    elif boundary.get("boundary_confidence") != "high":
        actions.append(_action(1, "confirm_provider", "Confirm your water provider",
            "Confirm the provider shown here using a recent water bill.",
            reason="The available service-area boundary is modeled or has limited provenance.",
            url=boundary.get("data_source")))

    if infrastructure.get("classification_status") != "officially_classified":
        actions.append(_action(2, "request_pipe_details", "Get more detail about your service line",
            "Ask your water provider whether it has a service-line inventory record for your address. You can also use its approved inspection process for a confirmed result.",
            reason="A validated property-level pipe record is not available in TapTrace yet.", url=provider_url))

    categories = {section["category"] for section in sections if section.get("measurements")}
    if "lead_and_plumbing_metals" in categories or (infrastructure.get("assessment") or {}).get("concern_level") in {"Moderate", "Elevated"}:
        actions.append(_action(2, "lead_filter", "Choose a filter certified for lead reduction",
            "If you want an added exposure-reduction step, choose a product certified for lead reduction and replace cartridges on schedule; certification must cover lead, not only taste or chlorine.",
            reason="Lead/plumbing-metal monitoring or infrastructure context appears in this profile.", url=EPA_LEAD_FILTERS))
    if "pfas" in categories or "unregulated_monitoring" in categories:
        actions.append(_action(2, "pfas_filter", "Match filtration to the reported PFAS",
            "Check the product's third-party certification and performance data for the specific PFAS reported; do not assume every carbon filter removes every PFAS.",
            reason="PFAS or other unregulated monitoring results appear in the available system data.", url=EPA_PFAS_FILTERS))
    if "microbial" in categories:
        actions.append(_action(1, "microbial_notice", "Follow official microbial and boil-water instructions",
            "Filtration is not a substitute for a current boil-water or do-not-drink notice. Follow the provider's instructions first.",
            reason="Microbial monitoring appears in the profile and official notices control immediate action."))

    if federal.get("current_violation_flag") or any(section["status"] == "attention" for section in sections):
        actions.append(_action(1, "review_utility_notice", "Review the current utility notice",
            "Follow the water provider's current instructions. Contact the provider if the notice does not explain what residents should do.",
            reason="A current federal violation flag or an above-benchmark/violation entry appears in the available system data.",
            url=report.get("landing_page_url") or report.get("report_url") or provider_url))

    if boundary and not ccr.get("has_validated_ccr"):
        actions.append(_action(2, "request_latest_report", "Open or request the latest water-quality report",
            "Use the provider link to find its Consumer Confidence Report, or ask the provider for the latest report and sampling dates.",
            reason="TapTrace has not yet checked and normalized this provider's latest report.",
            url=provider_url or epa_ccr_search))

    actions.append(_action(2, "home_testing", "Test at the tap for a home-specific answer",
        "Use a state-certified laboratory or an official local sampling program before drawing conclusions about water from this faucet.",
        reason="Utility monitoring describes the public water system and cannot measure conditions inside one home.", url=EPA_CERTIFIED_LABS))
    if report:
        actions.append(_action(3, "read_report", "Read the full provider report",
            "Check monitoring dates, sample locations, and the provider's explanations before choosing treatment equipment.",
            reason="The profile is a summary and does not replace the source report.", url=report.get("report_url")))
    return sorted(actions, key=lambda row: (row["priority"], row["type"]))
