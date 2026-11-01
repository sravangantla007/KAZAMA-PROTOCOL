"""Interactive and CLI runner for Kazama Protocol modules.

Usage:
    python cli_run.py --help
    python cli_run.py --query "What are the eligibility criteria and deadlines for NMES?" --decision "Apply for scholarship"
    python cli_run.py --mock
    python cli_run.py --interactive
"""
from __future__ import annotations
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.config import settings
from app.contracts.raw import UploadedFile, IngestionResult
from app.contracts.trusted import TrustedSource
from app.contracts.synthesis import SynthesisPayload
from app.contracts.decision import DecisionPayload
from app.modules.ingestion import ingest
from app.modules.weighter import weight
from app.modules.synthesizer import synthesize
from app.modules.decision import decide
from app.llm import get_llm_client
from app.llm.mock_client import MockLLMClient


TESTING_DIR = Path(__file__).parent / "testing"


def save_test_output(
    query: str,
    decision: Optional[str],
    urls: list[str],
    ingestion_result: IngestionResult,
    trusted_sources: list[TrustedSource],
    synthesis_payload: Optional[SynthesisPayload] = None,
    decision_payload: Optional[DecisionPayload] = None,
) -> Path:
    """Save test output JSON along with query and metadata into testing/ directory."""
    TESTING_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_slug = "".join(c if c.isalnum() else "_" for c in query[:30]).strip("_")
    filename = f"m1_m2_m3_m4_test_{timestamp}_{safe_slug}.json"
    file_path = TESTING_DIR / filename

    metadata: dict = {
        "query": query,
        "urls": urls,
        "mode": ingestion_result.mode,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "sources_count": len(ingestion_result.sources),
        "issues_count": len(ingestion_result.issues),
    }
    if decision:
        metadata["decision"] = decision

    data: dict = {
        "metadata": metadata,
        "ingestion_result": ingestion_result.model_dump(mode="json"),
        "trusted_sources": [s.model_dump(mode="json") for s in trusted_sources],
    }
    if synthesis_payload:
        data["synthesis"] = synthesis_payload.model_dump(mode="json")
    if decision_payload:
        data["decision"] = decision_payload.model_dump(mode="json")

    file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return file_path


async def run_pipeline(
    query: str,
    decision: Optional[str] = None,
    urls: list[str] | None = None,
    mock: bool = False,
    mock_scenario: str | None = None,
    today: Optional[date] = None,
):
    urls = urls or []
    eval_today = today or datetime.now(timezone.utc).date()
    print("\n" + "=" * 70)
    print(" KAZAMA PROTOCOL — DIGITAL DARK SPOT MODULE RUNNER")
    print("=" * 70)
    print(f"[*] Research Goal / Query: {query}")
    if decision:
        print(f"[*] Intended Decision     : {decision}")
    print(f"[*] Evaluation Date       : {eval_today.isoformat()}")
    print(f"[*] Mode                  : {'MOCK' if mock else 'LIVE'}")
    if urls:
        print(f"[*] Seed URLs  : {len(urls)} provided")
        for u in urls:
            print(f"    - {u}")
    print(f"[*] Search     : Provider={settings.search_provider} (Key set: {bool(settings.tavily_api_key or settings.search_api_key)})")
    print("-" * 70)

    # 1. Module 1: Ingestion
    print("\n[>>] Running Module 1 (Ingestion)...")
    start_time = datetime.now()
    ingestion_result = await ingest(
        query=query,
        urls=urls,
        files=[],
        mock_mode=mock,
        mock_scenario=mock_scenario,
    )
    duration_m1 = (datetime.now() - start_time).total_seconds()
    print(f"[OK] Ingestion completed in {duration_m1:.2f}s")
    print(f"[*] Total Sources Ingested: {len(ingestion_result.sources)}")
    print(f"[*] Total Issues Recorded : {len(ingestion_result.issues)}")

    # 2. Module 2: Weighter
    print("\n[>>] Running Module 2 (Weighter: Domain Trust & AI Detector)...")
    start_time_m2 = datetime.now()
    trusted_sources = weight(ingestion_result, today=eval_today)
    duration_m2 = (datetime.now() - start_time_m2).total_seconds()
    print(f"[OK] Weighting completed in {duration_m2:.4f}s")

    print("\n" + "-" * 70)
    print(" TRUSTED SOURCES RANKING (Sorted by Importance Score)")
    print("-" * 70)
    for rank, src in enumerate(trusted_sources, 1):
        print(f"#{rank} [{src.source_id}] Importance: {src.importance_score:.3f} | Baseline Trust: {src.baseline_trust_score:.3f}")
        print(f"   Domain Weight: {src.domain_weight:.2f} ({src.weight_breakdown.domain_rule_matched})")
        print(f"   AI Probability: {src.ai_probability_score:.2f} (Penalty: -{src.weight_breakdown.ai_penalty_applied:.3f})")
        print(f"   Type: {src.source_type} | Published Date: {src.published_date} (Age: {src.age_days or 'Unknown'} days)")
        print(f"   Target: {src.url_or_filename}")
        if src.title:
            print(f"   Title : {src.title}")
        sample = src.text[:120].replace('\n', ' ')
        print(f"   Sample: {sample}...")
        print()

    if ingestion_result.issues:
        print("-" * 70)
        print(" INGESTION ISSUES & WARNINGS")
        print("-" * 70)
        for issue in ingestion_result.issues:
            print(f"! [{issue.code}] on '{issue.target}': {issue.message}")

    # 3. Module 3: Synthesizer
    print("\n[>>] Running Module 3 (Synthesizer: Fact, Conflict & Gap Extraction)...")
    start_time_m3 = datetime.now()
    llm_client = MockLLMClient() if mock else get_llm_client()
    synthesis_payload = await synthesize(
        query=query,
        sources=trusted_sources,
        llm=llm_client,
        today=eval_today,
    )
    duration_m3 = (datetime.now() - start_time_m3).total_seconds()
    print(f"[OK] Synthesis completed in {duration_m3:.2f}s ({synthesis_payload.model_info['provider']} / {synthesis_payload.model_info['model']})")

    print("\n" + "-" * 70)
    print(" SYNTHESIS: TOPIC SUMMARY")
    print("-" * 70)
    print(synthesis_payload.topic_summary)

    print("\n" + "-" * 70)
    print(f" SYNTHESIS: FACTS ({len(synthesis_payload.facts)})")
    print("-" * 70)
    for fact in synthesis_payload.facts:
        print(f"[{fact.fact_id}] ({fact.category.upper()}) Confidence: {fact.confidence:.2f} (Corroborated by {fact.corroboration_count} source(s))")
        print(f"  Statement: {fact.statement}")
        for q in fact.supporting:
            print(f"  - Quote [{q.source_id}]: \"{q.quote}\"")
        print()

    print("-" * 70)
    print(f" SYNTHESIS: CONFLICTS ({len(synthesis_payload.conflicts)})")
    print("-" * 70)
    if synthesis_payload.conflicts:
        for conf in synthesis_payload.conflicts:
            print(f"[{conf.conflict_id}] Topic: {conf.topic} | Severity: {conf.severity}")
            print(f"  Note: {conf.note}")
            for c in conf.claims:
                print(f"  - Claim [{c.source_id}]: {c.claim}")
                print(f"    Quote: \"{c.quote}\"")
            print()
    else:
        print("No direct conflicts detected between sources.")

    print("-" * 70)
    print(f" SYNTHESIS: MISSING INFORMATION ({len(synthesis_payload.missing_information)})")
    print("-" * 70)
    if synthesis_payload.missing_information:
        for m in synthesis_payload.missing_information:
            print(f"[{m.missing_id}] Urgency: {m.importance} | {m.description}")
            print(f"  Why Expected: {m.why_expected}")
            print()
    else:
        print("No critical information gaps identified.")

    # 4. Module 4: Decision Engine
    print("\n[>>] Running Module 4 (Decision Engine: Decision-Specific Verification & Trust Scoring)...")
    start_time_m4 = datetime.now()
    decision_payload = await decide(
        query=query,
        decision=decision or "Assess information gaps and decide next steps",
        synthesis=synthesis_payload,
        sources=trusted_sources,
        llm=llm_client,
        today=eval_today,
    )
    duration_m4 = (datetime.now() - start_time_m4).total_seconds()
    print(f"[OK] Decision Engine completed in {duration_m4:.2f}s")

    print("\n" + "=" * 70)
    print(f" DECISION BRIEFING: {decision.upper() if decision else 'ASSESS READINESS'}")
    print("=" * 70)
    print(f"READINESS: {decision_payload.decision_readiness}")
    print(f"OVERALL TRUST SCORE: {decision_payload.overall_trust_score:.3f} [{decision_payload.trust_summary.overall_trust_label}]")
    comps = decision_payload.trust_summary.components
    print(f"  Components: Evidence Strength: {comps.get('evidence_strength', 0):.3f} | Conflict Penalty: -{comps.get('conflict_penalty', 0):.3f} | Missing Penalty: -{comps.get('missing_penalty', 0):.3f} | Staleness Penalty: -{comps.get('staleness_penalty', 0):.3f}")
    print(f"\nSUMMARY: {decision_payload.summary}\n")

    print("-" * 70)
    print(f" RELEVANT EVIDENCE ITEMS ({len(decision_payload.relevant_facts)})")
    print("-" * 70)
    for f in decision_payload.relevant_facts:
        time_tag = f"[{f.time_relevance.level}]"
        print(f"[{f.evidence_id}] ({f.provenance}) Confidence: {f.confidence:.2f} {time_tag}")
        print(f"  Claim: {f.statement}")
        print(f"  Why Matters: {f.relevance_to_decision}")
        print(f"  Time Note: {f.time_relevance.message}")
        for cit in f.citations:
            v_tag = "VERIFIED" if cit.quote_verified else "UNVERIFIED"
            print(f"  - [{cit.source_id}] ({v_tag}): \"{cit.quote}\"")
        print()

    print("-" * 70)
    print(f" CONFLICTING CLAIMS ({len(decision_payload.conflicting_claims)})")
    print("-" * 70)
    for conf in decision_payload.conflicting_claims:
        print(f"[{conf.conflict_id}] Topic: {conf.topic} | Severity: {conf.severity}")
        print(f"  Why Matters: {conf.why_it_matters_for_decision}")
        print(f"  Resolution : {conf.suggested_resolution}")
        for cl in conf.claims:
            v_tag = "VERIFIED" if cl.quote_verified else "UNVERIFIED"
            print(f"  - [{cl.source_id}] ({v_tag}): {cl.claim}")
            print(f"    Quote: \"{cl.quote}\"")
        print()

    print("-" * 70)
    print(f" MISSING INFORMATION GAPS ({len(decision_payload.missing_information)})")
    print("-" * 70)
    for m in decision_payload.missing_information:
        print(f"[{m.missing_id}] Importance: {m.importance} | {m.description}")
        print(f"  Why Matters: {m.why_it_matters_for_decision}")
        print(f"  Where to Look: {m.where_to_look}")
        print()

    print("-" * 70)
    print(f" ACTIONABLE VERIFICATION CHECKLIST ({len(decision_payload.actionable_verification_checklist)})")
    print("-" * 70)
    for it in decision_payload.actionable_verification_checklist:
        print(f"#{it.priority} [{it.item_id}] ({it.urgency}) ACTION: {it.action}")
        print(f"   Reason      : {it.reason}")
        print(f"   Verify With : {it.verify_with}")
        print(f"   Related IDs : {', '.join(it.related_ids) if it.related_ids else 'None'}")
        print()

    if decision_payload.warnings:
        print("-" * 70)
        print(" ENGINE WARNINGS")
        print("-" * 70)
        for w in decision_payload.warnings:
            print(f" [!] {w}")
        print()

    print("-" * 70)
    print(" DISCLAIMER")
    print("-" * 70)
    print(decision_payload.disclaimer)

    # Save to testing/ folder
    saved_path = save_test_output(query, decision, urls, ingestion_result, trusted_sources, synthesis_payload, decision_payload)
    print("-" * 70)
    print(f"[SAVED] Test outputs saved to: {saved_path.resolve()}")
    print("=" * 70 + "\n")
    return ingestion_result, trusted_sources, synthesis_payload, decision_payload, saved_path


async def interactive_mode():
    print("\n=== KAZAMA PROTOCOL CLI RUNNER ===")
    mock_input = input("Use mock mode? (y/N): ").strip().lower()
    mock = mock_input == "y"

    query = input("Enter research goal / topic / question: ").strip()
    if not query:
        query = "What should I verify before applying for the NMES scholarship?"
        print(f"Defaulting to: {query}")

    decision = input("Enter decision context (or press Enter for default): ").strip()
    if not decision:
        decision = "Apply in the current cycle"

    urls = []
    if not mock:
        urls_input = input("Enter seed URLs (comma-separated, or Enter to use search only): ").strip()
        if urls_input:
            urls = [u.strip() for u in urls_input.split(",") if u.strip()]

    await run_pipeline(query=query, decision=decision, urls=urls, mock=mock)


async def run_from_file(file_path: Path):
    if not file_path.exists():
        print(f"[ERROR] File not found: {file_path}")
        return

    content = json.loads(file_path.read_text(encoding="utf-8"))
    ingestion_data = content.get("ingestion_result", content)
    ingestion_result = IngestionResult.model_validate(ingestion_data)

    query = ingestion_result.query
    decision = content.get("metadata", {}).get("decision")

    print("\n" + "=" * 70)
    print(" KAZAMA PROTOCOL — RE-RUNNING MODULE 2 ON SAVED FILE")
    print("=" * 70)
    print(f"[*] Input File            : {file_path}")
    print(f"[*] Research Goal / Query: {query}")
    if decision:
        print(f"[*] Intended Decision     : {decision}")
    print(f"[*] Sources In File       : {len(ingestion_result.sources)}")
    print("-" * 70)

    print("\n[>>] Running Module 2 (Weighter: Domain Trust & AI Detector)...")
    start_time_m2 = datetime.now()
    trusted_sources = weight(ingestion_result, today=datetime.now(timezone.utc).date())
    duration_m2 = (datetime.now() - start_time_m2).total_seconds()
    print(f"[OK] Weighting completed in {duration_m2:.4f}s")

    print("\n" + "-" * 70)
    print(" TRUSTED SOURCES RANKING (Sorted by Importance Score)")
    print("-" * 70)
    for rank, src in enumerate(trusted_sources, 1):
        print(f"#{rank} [{src.source_id}] Importance: {src.importance_score:.3f} | Baseline Trust: {src.baseline_trust_score:.3f}")
        print(f"   Domain Weight: {src.domain_weight:.2f} ({src.weight_breakdown.domain_rule_matched})")
        print(f"   AI Probability: {src.ai_probability_score:.2f} (Penalty: -{src.weight_breakdown.ai_penalty_applied:.3f})")
        print(f"   Type: {src.source_type} | Published Date: {src.published_date} (Age: {src.age_days or 'Unknown'} days)")
        print(f"   Target: {src.url_or_filename}")
        if src.title:
            print(f"   Title : {src.title}")
        sample = src.text[:120].replace('\n', ' ')
        print(f"   Sample: {sample}...")
        print()

    # 3. Module 3: Synthesizer
    print("\n[>>] Running Module 3 (Synthesizer: Fact, Conflict & Gap Extraction)...")
    start_time_m3 = datetime.now()
    llm_client = get_llm_client()
    synthesis_payload = await synthesize(
        query=query,
        sources=trusted_sources,
        llm=llm_client,
        today=datetime.now(timezone.utc).date(),
    )
    duration_m3 = (datetime.now() - start_time_m3).total_seconds()
    print(f"[OK] Synthesis completed in {duration_m3:.2f}s ({synthesis_payload.model_info['provider']} / {synthesis_payload.model_info['model']})")

    print("\n" + "-" * 70)
    print(" SYNTHESIS: TOPIC SUMMARY")
    print("-" * 70)
    print(synthesis_payload.topic_summary)

    print("\n" + "-" * 70)
    print(f" SYNTHESIS: FACTS ({len(synthesis_payload.facts)})")
    print("-" * 70)
    for fact in synthesis_payload.facts:
        print(f"[{fact.fact_id}] ({fact.category.upper()}) Confidence: {fact.confidence:.2f} (Corroborated by {fact.corroboration_count} source(s))")
        print(f"  Statement: {fact.statement}")
        for q in fact.supporting:
            print(f"  - Quote [{q.source_id}]: \"{q.quote}\"")
        print()

    print("-" * 70)
    print(f" SYNTHESIS: CONFLICTS ({len(synthesis_payload.conflicts)})")
    print("-" * 70)
    if synthesis_payload.conflicts:
        for conf in synthesis_payload.conflicts:
            print(f"[{conf.conflict_id}] Topic: {conf.topic} | Severity: {conf.severity}")
            print(f"  Note: {conf.note}")
            for c in conf.claims:
                print(f"  - Claim [{c.source_id}]: {c.claim}")
                print(f"    Quote: \"{c.quote}\"")
            print()
    else:
        print("No direct conflicts detected between sources.")

    print("-" * 70)
    print(f" SYNTHESIS: MISSING INFORMATION ({len(synthesis_payload.missing_information)})")
    print("-" * 70)
    if synthesis_payload.missing_information:
        for m in synthesis_payload.missing_information:
            print(f"[{m.missing_id}] Urgency: {m.importance} | {m.description}")
            print(f"  Why Expected: {m.why_expected}")
            print()
    else:
        print("No critical information gaps identified.")

    # 4. Module 4: Decision Engine
    print("\n[>>] Running Module 4 (Decision Engine: Decision-Specific Verification & Trust Scoring)...")
    start_time_m4 = datetime.now()
    decision_payload = await decide(
        query=query,
        decision=decision or "Assess information gaps and decide next steps",
        synthesis=synthesis_payload,
        sources=trusted_sources,
        llm=llm_client,
        today=eval_today,
    )
    duration_m4 = (datetime.now() - start_time_m4).total_seconds()
    print(f"[OK] Decision Engine completed in {duration_m4:.2f}s")

    print("\n" + "=" * 70)
    print(f" DECISION BRIEFING: {decision.upper() if decision else 'ASSESS READINESS'}")
    print("=" * 70)
    print(f"READINESS: {decision_payload.decision_readiness}")
    print(f"OVERALL TRUST SCORE: {decision_payload.overall_trust_score:.3f} [{decision_payload.trust_summary.overall_trust_label}]")
    comps = decision_payload.trust_summary.components
    print(f"  Components: Evidence Strength: {comps.get('evidence_strength', 0):.3f} | Conflict Penalty: -{comps.get('conflict_penalty', 0):.3f} | Missing Penalty: -{comps.get('missing_penalty', 0):.3f} | Staleness Penalty: -{comps.get('staleness_penalty', 0):.3f}")
    print(f"\nSUMMARY: {decision_payload.summary}\n")

    print("-" * 70)
    print(f" RELEVANT EVIDENCE ITEMS ({len(decision_payload.relevant_facts)})")
    print("-" * 70)
    for f in decision_payload.relevant_facts:
        time_tag = f"[{f.time_relevance.level}]"
        print(f"[{f.evidence_id}] ({f.provenance}) Confidence: {f.confidence:.2f} {time_tag}")
        print(f"  Claim: {f.statement}")
        print(f"  Why Matters: {f.relevance_to_decision}")
        print(f"  Time Note: {f.time_relevance.message}")
        for cit in f.citations:
            v_tag = "VERIFIED" if cit.quote_verified else "UNVERIFIED"
            print(f"  - [{cit.source_id}] ({v_tag}): \"{cit.quote}\"")
        print()

    print("-" * 70)
    print(f" CONFLICTING CLAIMS ({len(decision_payload.conflicting_claims)})")
    print("-" * 70)
    for conf in decision_payload.conflicting_claims:
        print(f"[{conf.conflict_id}] Topic: {conf.topic} | Severity: {conf.severity}")
        print(f"  Why Matters: {conf.why_it_matters_for_decision}")
        print(f"  Resolution : {conf.suggested_resolution}")
        for cl in conf.claims:
            v_tag = "VERIFIED" if cl.quote_verified else "UNVERIFIED"
            print(f"  - [{cl.source_id}] ({v_tag}): {cl.claim}")
            print(f"    Quote: \"{cl.quote}\"")
        print()

    print("-" * 70)
    print(f" MISSING INFORMATION GAPS ({len(decision_payload.missing_information)})")
    print("-" * 70)
    for m in decision_payload.missing_information:
        print(f"[{m.missing_id}] Importance: {m.importance} | {m.description}")
        print(f"  Why Matters: {m.why_it_matters_for_decision}")
        print(f"  Where to Look: {m.where_to_look}")
        print()

    print("-" * 70)
    print(f" ACTIONABLE VERIFICATION CHECKLIST ({len(decision_payload.actionable_verification_checklist)})")
    print("-" * 70)
    for it in decision_payload.actionable_verification_checklist:
        print(f"#{it.priority} [{it.item_id}] ({it.urgency}) ACTION: {it.action}")
        print(f"   Reason      : {it.reason}")
        print(f"   Verify With : {it.verify_with}")
        print(f"   Related IDs : {', '.join(it.related_ids) if it.related_ids else 'None'}")
        print()

    if decision_payload.warnings:
        print("-" * 70)
        print(" ENGINE WARNINGS")
        print("-" * 70)
        for w in decision_payload.warnings:
            print(f" [!] {w}")
        print()

    print("-" * 70)
    print(" DISCLAIMER")
    print("-" * 70)
    print(decision_payload.disclaimer)

    # Save output
    saved_path = save_test_output(query, decision, [], ingestion_result, trusted_sources, synthesis_payload, decision_payload)
    print("-" * 70)
    print(f"[SAVED] Pipeline outputs saved to: {saved_path.resolve()}")
    print("=" * 70 + "\n")
    return trusted_sources, synthesis_payload, decision_payload, saved_path


def main():
    parser = argparse.ArgumentParser(description="Kazama Protocol CLI Module Runner")
    parser.add_argument("--query", "-q", type=str, help="Research goal / topic / question")
    parser.add_argument("--decision", "-d", type=str, default="Assess information gaps and decide next steps", help="Decision context")
    parser.add_argument("--today", "-t", type=str, help="Simulation date in YYYY-MM-DD (default: current system date)")
    parser.add_argument("--urls", "-u", nargs="*", default=[], help="Seed URLs to ingest")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode using mock fixtures")
    parser.add_argument("--scenario", type=str, default="scholarship_scenario", help="Mock scenario name")
    parser.add_argument("--from-file", "-f", type=str, help="Load an existing IngestionResult JSON and run Module 2")
    parser.add_argument("--interactive", "-i", action="store_true", help="Run interactive prompt")

    args = parser.parse_args()

    if args.from_file:
        asyncio.run(run_from_file(Path(args.from_file)))
    elif args.interactive or (len(sys.argv) == 1):
        asyncio.run(interactive_mode())
    else:
        query = args.query or "What should I verify before applying for the NMES scholarship?"
        asyncio.run(run_pipeline(
            query=query,
            decision=args.decision,
            urls=args.urls,
            mock=args.mock,
            mock_scenario=args.scenario,
        ))


if __name__ == "__main__":
    main()

