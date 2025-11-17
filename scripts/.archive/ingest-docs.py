#!/usr/bin/env python3
"""
Document Ingestion Script for HomeSight RAG

This script ingests manufacturer manuals, maintenance guides, and building codes
into the RAG vector database.

Usage:
    python scripts/ingest-docs.py [--docs-dir /path/to/docs] [--clear]
"""

import sys
import argparse
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "ai-sidecar"))

from rag_engine import RAGEngine
import pypdf


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text content from PDF file"""
    try:
        reader = pypdf.PdfReader(str(pdf_path))
        text_parts = []
        
        for page_num, page in enumerate(reader.pages):
            text = page.extract_text()
            if text.strip():
                text_parts.append(f"[Page {page_num + 1}]\n{text}")
        
        return "\n\n".join(text_parts)
    except Exception as e:
        print(f"❌ Error reading PDF {pdf_path.name}: {e}")
        return ""


def ingest_sample_documents(rag: RAGEngine):
    """Ingest sample home maintenance documents (for demo/testing)"""
    print("📚 Adding sample home maintenance documents...")
    
    docs = [
        {
            "text": """
            Aqara Water Leak Sensor - User Manual
            
            Installation:
            1. Remove the protective film from the sensor probe
            2. Place sensor in areas prone to water leaks (near water heaters, under sinks, washing machines)
            3. Ensure probe contacts are touching the floor
            4. Press button on top to pair with hub
            
            Specifications:
            - Battery: CR2032 (lasts 2+ years)
            - Detection time: < 60 seconds
            - Operating temperature: -10°C to 60°C
            - Wireless protocol: Zigbee 3.0
            
            Troubleshooting:
            - If sensor doesn't respond: Replace battery
            - If false alarms occur: Check for condensation on probe, clean contacts
            - If sensor falls offline: Check hub connection, re-pair device
            
            Maintenance:
            - Replace battery every 2 years
            - Clean sensor probe monthly with dry cloth
            - Test sensor quarterly by placing in shallow water
            """,
            "source": "Aqara Water Leak Sensor Manual",
            "category": "device_manual",
            "device_type": "water_sensor"
        },
        {
            "text": """
            Emergency Plumbing Guide - Water Leaks
            
            IMMEDIATE ACTIONS FOR WATER LEAKS:
            
            1. SHUT OFF WATER
               - Main shutoff: Usually in basement near water meter or street-side wall
               - Turn valve clockwise until fully closed
               - If frozen, use emergency shutoff outside
            
            2. ELECTRICAL SAFETY
               - DO NOT touch electrical outlets/switches near water
               - Turn off power at circuit breaker if water near outlets
               - Call electrician if water has reached electrical panel
            
            3. DAMAGE MITIGATION
               - Move furniture and valuables away from water
               - Place buckets under active drips
               - Use mops/towels to contain water spread
               - Open windows to improve ventilation
               - Document damage with photos for insurance
            
            4. IDENTIFY SOURCE
               Common sources:
               - Water heater: Check T&P relief valve, tank bottom for rust
               - Supply lines: Look for corroded connections, burst hoses
               - Drain pipes: Check for cracks, loose connections
               - Toilets: Check wax ring, supply line, tank bolts
               - Appliances: Washing machine hoses, dishwasher connections
            
            5. CALL PROFESSIONALS
               - Plumber for pipe repairs, water heater replacement
               - Water damage restoration for extensive flooding
               - Insurance company within 24 hours
            
            PREVENTION:
               - Install water sensors near water heater, sump pump, washing machine
               - Replace washing machine hoses every 5 years
               - Inspect water heater annually
               - Know location of main water shutoff
            """,
            "source": "Plumbing Emergency Guide",
            "category": "maintenance_guide",
            "emergency": "true"
        },
        {
            "text": """
            Water Heater Maintenance Guide
            
            TEMPERATURE & PRESSURE RELIEF VALVE (T&P Valve):
            
            Function:
            - Prevents excessive pressure buildup in tank
            - Opens automatically if pressure exceeds 150 PSI or temp exceeds 210°F
            - Critical safety device - must be in working condition
            
            Testing (every 6 months):
            1. Place bucket under discharge pipe
            2. Lift lever on T&P valve partially
            3. Water should flow freely from discharge pipe
            4. Release lever - water should stop
            5. If valve doesn't open or doesn't close: REPLACE IMMEDIATELY
            
            Common T&P Valve Issues:
            - Dripping from discharge pipe: Thermal expansion, high pressure, or failed valve
            - No water when tested: Valve may be seized - replace
            - Continuous flow: Failed valve - replace immediately
            
            If T&P Valve Discharges:
            1. Turn off power/gas to water heater
            2. Turn off cold water supply to tank
            3. Open hot water faucet to release pressure
            4. Call plumber to inspect
            5. DO NOT plug discharge pipe or cap valve
            
            ANNUAL MAINTENANCE:
            - Drain 2-3 gallons from tank to remove sediment
            - Check anode rod (replace if < 6 inches or heavily corroded)
            - Inspect for rust, corrosion, or leaks
            - Test T&P valve
            - Verify proper venting (gas heaters)
            
            SIGNS OF FAILURE:
            - Rusty water from hot taps
            - Rumbling/popping sounds (sediment buildup)
            - Water pooling around base
            - Age > 10 years
            
            EMERGENCY SHUTDOWN:
            Electric: Turn off breaker
            Gas: Turn gas valve to "OFF", turn off gas supply at meter if leak suspected
            All: Close cold water supply valve to tank
            """,
            "source": "Water Heater Maintenance Manual",
            "category": "maintenance_guide",
            "device_type": "water_heater"
        },
        {
            "text": """
            International Residential Code (IRC) - Plumbing Requirements
            
            Section P2801.5 - Flood Resistance
            In flood hazard areas, water heaters, plumbing fixtures, and equipment shall be
            located or installed in accordance with Section R322.
            
            Section P2801.6 - Piping Support
            Piping shall be supported in accordance with manufacturer's installation instructions.
            
            Section P2903.3.2 - Water Hammer
            Water-hammer arrestors shall be installed where quick-acting valves are utilized.
            Arrestors shall be sized in accordance with manufacturer's specifications.
            
            Section P2904.6.3 - Pressure Relief Requirements
            Storage water heaters and hot water storage tanks shall be provided with pressure
            relief valves installed in accordance with manufacturer's installation instructions.
            Relief valves shall be set to open at not more than 150 psi.
            
            Section P2904.6.4 - Discharge
            The discharge piping serving pressure relief valves shall:
            1. Be of materials approved for hot water distribution
            2. Be sized to meet or exceed the pipe size of the relief valve outlet
            3. Discharge to an approved location
            4. Not be trapped or have any valves
            5. Discharge through an air gap into a waste receptor or floor drain
            6. Be installed to allow complete drainage
            
            Section P2904.6.5 - Required Pan
            Where water heaters are installed in locations where leakage could cause damage,
            the water heater shall be installed in a galvanized steel pan with a minimum
            depth of 1.5 inches or other approved pan.
            
            Section P2801.1 - Water Supply Protection
            A backflow preventer shall be installed on lawn irrigation systems.
            """,
            "source": "International Residential Code - Plumbing Sections",
            "category": "building_code"
        },
        {
            "text": """
            Home Winterization Guide - Freeze Prevention
            
            CRITICAL: Freeze protection must be in place before temperatures drop below 32°F
            
            PIPE FREEZE PREVENTION:
            
            Vulnerable Areas:
            - Exterior walls (especially north-facing)
            - Unheated spaces (attics, basements, crawl spaces, garages)
            - Kitchen/bathroom cabinets on exterior walls
            - Outdoor spigots and hose bibs
            - Swimming pool supply lines
            
            Protection Methods:
            1. Insulation
               - Wrap pipes with foam pipe insulation (minimum R-3 rating)
               - Use heat tape on exposed pipes (follow manufacturer instructions)
               - Seal air leaks around pipes with caulk or spray foam
               - Insulate rim joists and foundation walls
            
            2. Maintain Temperature
               - Keep thermostat at minimum 55°F when away
               - Open cabinet doors to allow warm air circulation
               - Keep garage doors closed if water lines present
               - Use space heaters in crawl spaces (with caution)
            
            3. Water Flow
               - Let faucets drip during extreme cold (hot AND cold sides)
               - Run water through rarely used fixtures weekly
               - Circulate water in rarely used areas
            
            4. Outdoor Protection
               - Disconnect and drain garden hoses
               - Shut off and drain outdoor spigots
               - Install insulated covers on hose bibs
               - Drain swimming pool lines or add antifreeze
            
            IF PIPES FREEZE:
            - Keep faucet open (relieves pressure as ice melts)
            - Apply heat: Hair dryer, heat lamp, warm towels
            - NEVER use open flame or propane torch
            - Work from faucet back toward frozen area
            - If you can't locate freeze or pipes have burst: Call plumber
            - Know location of main water shutoff
            
            WATER HEATER IN COLD AREAS:
            - Insulate tank with jacket (if manufacturer allows)
            - Insulate hot water pipes
            - Drain and winterize if in unheated space during vacancy
            - Consider tankless or power-vented models for cold locations
            
            PREVENTION SCHEDULE:
            - October: Complete all winterization tasks
            - November-March: Monitor temperatures, check vulnerable areas weekly
            - When temps drop below 20°F: Let faucets drip, increase vigilance
            - Spring: Remove insulated covers, reconnect hoses, test outdoor spigots
            """,
            "source": "Home Winterization and Freeze Prevention Guide",
            "category": "maintenance_guide",
            "seasonal": "winter"
        }
    ]
    
    for i, doc in enumerate(docs, 1):
        rag.add_document(
            text=doc["text"],
            metadata=doc
        )
        print(f"  ✅ {i}/{len(docs)}: {doc['source']}")
    
    print(f"\n✅ Added {len(docs)} sample documents")


def ingest_directory(rag: RAGEngine, docs_dir: Path):
    """Ingest all PDF files from a directory"""
    if not docs_dir.exists():
        print(f"❌ Directory not found: {docs_dir}")
        return
    
    pdf_files = list(docs_dir.glob("**/*.pdf"))
    if not pdf_files:
        print(f"⚠️  No PDF files found in {docs_dir}")
        return
    
    print(f"📂 Found {len(pdf_files)} PDF files in {docs_dir}")
    
    for i, pdf_path in enumerate(pdf_files, 1):
        print(f"\n[{i}/{len(pdf_files)}] Processing: {pdf_path.name}")
        
        text = extract_text_from_pdf(pdf_path)
        if not text:
            continue
        
        # Determine category from directory structure
        category = "document"
        if "manual" in str(pdf_path).lower():
            category = "device_manual"
        elif "maintenance" in str(pdf_path).lower() or "guide" in str(pdf_path).lower():
            category = "maintenance_guide"
        elif "code" in str(pdf_path).lower():
            category = "building_code"
        
        metadata = {
            "source": pdf_path.name,
            "category": category,
            "file_path": str(pdf_path)
        }
        
        # Split large documents into chunks (to stay under embedding limits)
        chunk_size = 2000  # characters
        chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
        
        for chunk_num, chunk in enumerate(chunks):
            chunk_metadata = metadata.copy()
            chunk_metadata["chunk"] = chunk_num + 1
            chunk_metadata["total_chunks"] = len(chunks)
            
            rag.add_document(text=chunk, metadata=chunk_metadata)
        
        print(f"  ✅ Added {len(chunks)} chunk(s) from {pdf_path.name}")
    
    print(f"\n✅ Ingestion complete!")


def main():
    parser = argparse.ArgumentParser(description="Ingest documents into HomeSight RAG")
    parser.add_argument(
        "--docs-dir",
        type=Path,
        help="Directory containing PDF documents to ingest"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing documents before ingesting"
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Add sample documents (for testing)"
    )
    parser.add_argument(
        "--rag-dir",
        type=Path,
        default=Path("/var/lib/homesight/rag"),
        help="RAG database directory (default: /var/lib/homesight/rag)"
    )
    
    args = parser.parse_args()
    
    print("🚀 HomeSight Document Ingestion")
    print("=" * 50)
    
    # Initialize RAG engine
    rag_path = args.rag_dir
    
    # Try system path first, fall back to local if permission denied
    try:
        rag_path.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        print(f"⚠️  Permission denied for {rag_path}, using local directory")
        rag_path = Path(__file__).parent.parent / "data" / "rag"
        rag_path.mkdir(parents=True, exist_ok=True)
    
    print(f"📍 RAG database: {rag_path}")
    rag = RAGEngine(persist_directory=str(rag_path))
    
    # Show current stats
    stats = rag.get_stats()
    print(f"📊 Current stats: {stats['total_documents']} documents indexed\n")
    
    if args.clear:
        confirm = input("⚠️  Clear all existing documents? (yes/no): ")
        if confirm.lower() == "yes":
            # TODO: Add clear method to RAGEngine
            print("❌ Clear functionality not yet implemented")
            return
    
    # Ingest documents
    if args.sample:
        ingest_sample_documents(rag)
    elif args.docs_dir:
        ingest_directory(rag, args.docs_dir)
    else:
        print("⚠️  No documents specified. Use --sample or --docs-dir")
        print("\nUsage examples:")
        print("  python scripts/ingest-docs.py --sample")
        print("  python scripts/ingest-docs.py --docs-dir /path/to/manuals")
    
    # Show final stats
    print("\n" + "=" * 50)
    stats = rag.get_stats()
    print(f"📊 Final stats: {stats['total_documents']} documents in RAG database")
    print(f"✅ RAG engine ready at: {rag_path}")


if __name__ == "__main__":
    main()
